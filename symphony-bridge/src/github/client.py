"""
GitHub API Client for Symphony PR Bridge.

Provides REST API wrapper with authentication, rate limiting, and error handling.
Supports both Personal Access Tokens and GitHub App authentication.
"""

import os
import time
import json
import hmac
import hashlib
import logging
from typing import Optional, Dict, List, Any, Union
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urljoin, parse_qs, urlparse
import base64

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class GitHubError(Exception):
    """Base exception for GitHub API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body or {}


class GitHubRateLimitError(GitHubError):
    """Raised when GitHub API rate limit is exceeded."""
    pass


class GitHubAuthError(GitHubError):
    """Raised when authentication fails."""
    pass


class GitHubNotFoundError(GitHubError):
    """Raised when a resource is not found."""
    pass


class GitHubValidationError(GitHubError):
    """Raised when request validation fails."""
    pass


@dataclass
class RateLimitInfo:
    """GitHub API rate limit information."""
    limit: int
    remaining: int
    reset_timestamp: int
    used: int
    
    @property
    def reset_datetime(self) -> datetime:
        """Convert reset timestamp to datetime."""
        return datetime.fromtimestamp(self.reset_timestamp)
    
    @property
    def seconds_until_reset(self) -> int:
        """Calculate seconds until rate limit resets."""
        return max(0, self.reset_timestamp - int(time.time()))
    
    @property
    def is_exhausted(self) -> bool:
        """Check if rate limit is exhausted."""
        return self.remaining <= 0


@dataclass
class PullRequest:
    """Represents a GitHub Pull Request."""
    number: int
    title: str
    body: Optional[str]
    state: str
    head_ref: str
    base_ref: str
    head_sha: str
    base_sha: str
    user_login: str
    html_url: str
    draft: bool
    merged: bool
    mergeable: Optional[bool]
    mergeable_state: Optional[str]
    labels: List[str]
    created_at: str
    updated_at: str
    closed_at: Optional[str] = None
    merged_at: Optional[str] = None
    
    @classmethod
    def from_api_response(cls, data: dict) -> "PullRequest":
        """Create PullRequest from GitHub API response."""
        return cls(
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            head_ref=data["head"]["ref"],
            base_ref=data["base"]["ref"],
            head_sha=data["head"]["sha"],
            base_sha=data["base"]["sha"],
            user_login=data["user"]["login"],
            html_url=data["html_url"],
            draft=data.get("draft", False),
            merged=data.get("merged", False),
            mergeable=data.get("mergeable"),
            mergeable_state=data.get("mergeable_state"),
            labels=[label["name"] for label in data.get("labels", [])],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            closed_at=data.get("closed_at"),
            merged_at=data.get("merged_at"),
        )


class GitHubClient:
    """
    GitHub API client with authentication, rate limiting, and error handling.
    
    Supports:
    - Personal Access Token (PAT) authentication
    - GitHub App authentication (JWT + installation tokens)
    - Rate limit tracking and backoff
    - Automatic retries with exponential backoff
    """
    
    DEFAULT_BASE_URL = "https://api.github.com"
    DEFAULT_TIMEOUT = 30
    DEFAULT_MAX_RETRIES = 3
    
    def __init__(
        self,
        token: Optional[str] = None,
        app_id: Optional[str] = None,
        private_key: Optional[str] = None,
        installation_id: Optional[int] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        """
        Initialize GitHub client.
        
        Args:
            token: Personal Access Token or installation token
            app_id: GitHub App ID (for App authentication)
            private_key: GitHub App private key PEM content (for App authentication)
            installation_id: GitHub App installation ID (for App authentication)
            base_url: GitHub API base URL
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_API_KEY")
        self.app_id = app_id or os.environ.get("GITHUB_APP_ID")
        self.private_key = private_key or self._load_private_key_from_env()
        self.installation_id = installation_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        
        self._session: Optional[requests.Session] = None
        self._installation_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._rate_limit_info: Optional[RateLimitInfo] = None
        self._jwt_token: Optional[str] = None
        self._jwt_expires_at: Optional[datetime] = None
        
        if not self.token and not (self.app_id and self.private_key):
            raise GitHubAuthError(
                "Either token or app_id + private_key must be provided"
            )
    
    def _load_private_key_from_env(self) -> Optional[str]:
        """Load private key from environment variable or file."""
        key_content = os.environ.get("GITHUB_APP_PRIVATE_KEY")
        if key_content:
            return key_content
        
        key_path = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH")
        if key_path and os.path.exists(key_path):
            with open(key_path, "r") as f:
                return f.read()
        
        return None
    
    def _create_session(self) -> requests.Session:
        """Create configured requests session with retries."""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PATCH", "PUT", "DELETE"],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session
    
    @property
    def session(self) -> requests.Session:
        """Get or create requests session."""
        if self._session is None:
            self._session = self._create_session()
        return self._session
    
    def _generate_jwt(self) -> str:
        """Generate JWT for GitHub App authentication."""
        import jwt
        
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=10)
        
        payload = {
            "iat": now,
            "exp": expires_at,
            "iss": self.app_id,
        }
        
        token = jwt.encode(payload, self.private_key, algorithm="RS256")
        self._jwt_token = token
        self._jwt_expires_at = expires_at
        
        return token
    
    def _get_jwt(self) -> str:
        """Get valid JWT, generating a new one if necessary."""
        if self._jwt_token and self._jwt_expires_at and datetime.utcnow() < self._jwt_expires_at - timedelta(minutes=1):
            return self._jwt_token
        return self._generate_jwt()
    
    def _get_installation_token(self) -> str:
        """Get installation token for GitHub App authentication."""
        if self._installation_token and self._token_expires_at and datetime.utcnow() < self._token_expires_at - timedelta(minutes=1):
            return self._installation_token
        
        if not self.installation_id:
            raise GitHubAuthError("installation_id is required for GitHub App authentication")
        
        jwt_token = self._get_jwt()
        url = f"{self.base_url}/app/installations/{self.installation_id}/access_tokens"
        
        response = self.session.post(
            url,
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=self.timeout,
        )
        
        if response.status_code != 201:
            raise GitHubAuthError(
                f"Failed to get installation token: {response.status_code} - {response.text}"
            )
        
        data = response.json()
        self._installation_token = data["token"]
        self._token_expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        
        return self._installation_token
    
    def _get_auth_token(self) -> str:
        """Get authentication token (PAT or installation token)."""
        if self.token:
            return self.token
        return self._get_installation_token()
    
    def _update_rate_limit(self, headers: dict):
        """Update rate limit info from response headers."""
        try:
            self._rate_limit_info = RateLimitInfo(
                limit=int(headers.get("X-RateLimit-Limit", 0)),
                remaining=int(headers.get("X-RateLimit-Remaining", 0)),
                reset_timestamp=int(headers.get("X-RateLimit-Reset", 0)),
                used=int(headers.get("X-RateLimit-Used", 0)),
            )
        except (ValueError, TypeError):
            pass
    
    def _wait_for_rate_limit(self):
        """Wait if rate limit is exhausted."""
        if self._rate_limit_info and self._rate_limit_info.is_exhausted:
            sleep_seconds = self._rate_limit_info.seconds_until_reset + 1
            logger.warning(f"Rate limit exhausted. Waiting {sleep_seconds} seconds...")
            time.sleep(sleep_seconds)
    
    def _handle_error(self, response: requests.Response):
        """Handle API error responses."""
        status_code = response.status_code
        
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = {"message": response.text}
        
        message = body.get("message", "Unknown error")
        
        if status_code == 404:
            raise GitHubNotFoundError(message, status_code, body)
        elif status_code == 401:
            raise GitHubAuthError(message, status_code, body)
        elif status_code == 403:
            if "rate limit" in message.lower():
                raise GitHubRateLimitError(message, status_code, body)
            raise GitHubError(message, status_code, body)
        elif status_code == 422:
            raise GitHubValidationError(message, status_code, body)
        else:
            raise GitHubError(message, status_code, body)
    
    def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[dict] = None,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        """
        Make authenticated request to GitHub API.
        
        Args:
            method: HTTP method
            endpoint: API endpoint (relative to base URL)
            json_data: JSON request body
            params: Query parameters
            headers: Additional headers
            
        Returns:
            Response JSON as dictionary
        """
        self._wait_for_rate_limit()
        
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        
        request_headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {self._get_auth_token()}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        
        if headers:
            request_headers.update(headers)
        
        logger.debug(f"{method} {url}")
        
        response = self.session.request(
            method=method,
            url=url,
            json=json_data,
            params=params,
            headers=request_headers,
            timeout=self.timeout,
        )
        
        self._update_rate_limit(response.headers)
        
        if response.status_code >= 400:
            self._handle_error(response)
        
        if response.status_code == 204 or not response.content:
            return {}
        
        return response.json()
    
    def get_rate_limit(self) -> RateLimitInfo:
        """Get current rate limit status."""
        data = self._request("GET", "/rate_limit")
        core = data.get("resources", {}).get("core", {})
        return RateLimitInfo(
            limit=core.get("limit", 0),
            remaining=core.get("remaining", 0),
            reset_timestamp=core.get("reset", 0),
            used=core.get("used", 0),
        )
    
    # =========================================================================
    # Pull Request Methods
    # =========================================================================
    
    def create_pr(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: Optional[str] = None,
        draft: bool = False,
        maintainer_can_modify: bool = True,
    ) -> PullRequest:
        """
        Create a new pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            title: PR title
            head: Branch containing changes
            base: Branch to merge into
            body: PR description
            draft: Create as draft PR
            maintainer_can_modify: Allow maintainers to modify
            
        Returns:
            Created PullRequest
        """
        data = {
            "title": title,
            "head": head,
            "base": base,
            "draft": draft,
            "maintainer_can_modify": maintainer_can_modify,
        }
        
        if body:
            data["body"] = body
        
        response = self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            json_data=data,
        )
        
        return PullRequest.from_api_response(response)
    
    def update_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
        base: Optional[str] = None,
        maintainer_can_modify: Optional[bool] = None,
    ) -> PullRequest:
        """
        Update an existing pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            title: New title
            body: New description
            state: New state ("open" or "closed")
            base: New base branch
            maintainer_can_modify: Allow maintainers to modify
            
        Returns:
            Updated PullRequest
        """
        data = {}
        
        if title is not None:
            data["title"] = title
        if body is not None:
            data["body"] = body
        if state is not None:
            data["state"] = state
        if base is not None:
            data["base"] = base
        if maintainer_can_modify is not None:
            data["maintainer_can_modify"] = maintainer_can_modify
        
        response = self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            json_data=data,
        )
        
        return PullRequest.from_api_response(response)
    
    def get_pr(self, owner: str, repo: str, pr_number: int) -> PullRequest:
        """
        Get a pull request by number.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            
        Returns:
            PullRequest
        """
        response = self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
        )
        
        return PullRequest.from_api_response(response)
    
    def list_prs(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        head: Optional[str] = None,
        base: Optional[str] = None,
        sort: str = "created",
        direction: str = "desc",
        per_page: int = 30,
        page: int = 1,
    ) -> List[PullRequest]:
        """
        List pull requests for a repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            state: Filter by state ("open", "closed", "all")
            head: Filter by head branch (format: "user:branch")
            base: Filter by base branch
            sort: Sort field ("created", "updated", "popularity", "long-running")
            direction: Sort direction ("asc", "desc")
            per_page: Results per page (max 100)
            page: Page number
            
        Returns:
            List of PullRequests
        """
        params = {
            "state": state,
            "sort": sort,
            "direction": direction,
            "per_page": per_page,
            "page": page,
        }
        
        if head:
            params["head"] = head
        if base:
            params["base"] = base
        
        response = self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls",
            params=params,
        )
        
        return [PullRequest.from_api_response(pr) for pr in response]
    
    def close(self):
        """Close the HTTP session."""
        if self._session:
            self._session.close()
            self._session = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

"""
Git Operations Module

Handles all git-related operations for the DevClaw runner.
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class GitError(Exception):
    """Base exception for git operations."""
    pass


class GitCloneError(GitError):
    """Raised when git clone fails."""
    pass


class GitCheckoutError(GitError):
    """Raised when git checkout fails."""
    pass


class GitCommitError(GitError):
    """Raised when git commit fails."""
    pass


class GitPushError(GitError):
    """Raised when git push fails."""
    pass


@dataclass
class GitConfig:
    """Configuration for git operations."""
    user_name: str = "DevClaw Runner"
    user_email: str = "devclaw@openclaw.local"
    default_branch: str = "main"
    ssh_key_path: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> 'GitConfig':
        """Create config from environment variables."""
        return cls(
            user_name=os.environ.get('DEVCLAW_GIT_USER_NAME', cls.user_name),
            user_email=os.environ.get('DEVCLAW_GIT_USER_EMAIL', cls.user_email),
            default_branch=os.environ.get('DEVCLAW_GIT_DEFAULT_BRANCH', cls.default_branch),
            ssh_key_path=os.environ.get('DEVCLAW_SSH_KEY_PATH')
        )


class GitOperations:
    """
    Handles all git operations for the DevClaw runner.
    
    Features:
    - Clone repositories
    - Checkout and create branches
    - Commit changes
    - Push changes
    - Handle authentication
    """
    
    def __init__(self, config: Optional[GitConfig] = None):
        self.config = config or GitConfig.from_env()
        self._env = self._prepare_env()
    
    def _prepare_env(self) -> Dict[str, str]:
        """Prepare environment variables for git commands."""
        env = os.environ.copy()
        
        # Configure git user if not already set
        env['GIT_AUTHOR_NAME'] = self.config.user_name
        env['GIT_AUTHOR_EMAIL'] = self.config.user_email
        env['GIT_COMMITTER_NAME'] = self.config.user_name
        env['GIT_COMMITTER_EMAIL'] = self.config.user_email
        
        # Configure SSH if key path provided
        if self.config.ssh_key_path:
            env['GIT_SSH_COMMAND'] = f'ssh -i {self.config.ssh_key_path} -o StrictHostKeyChecking=no'
        
        return env
    
    def _run_git(
        self,
        args: List[str],
        cwd: Optional[str] = None,
        check: bool = True,
        capture_output: bool = True,
        timeout: int = 300
    ) -> subprocess.CompletedProcess:
        """
        Run a git command.
        
        Args:
            args: Git command arguments (without 'git')
            cwd: Working directory
            check: Raise exception on non-zero exit
            capture_output: Capture stdout/stderr
            timeout: Command timeout in seconds
            
        Returns:
            CompletedProcess instance
        """
        cmd = ['git'] + args
        logger.debug(f"Running git command: {' '.join(cmd)} in {cwd or 'current directory'}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                env=self._env,
                capture_output=capture_output,
                text=True,
                check=False,
                timeout=timeout
            )
            
            if check and result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else f"Git command failed with code {result.returncode}"
                logger.error(f"Git command failed: {error_msg}")
                raise GitError(f"Git command failed: {error_msg}")
            
            return result
            
        except subprocess.TimeoutExpired as e:
            logger.error(f"Git command timed out after {timeout}s")
            raise GitError(f"Git command timed out after {timeout}s") from e
        except subprocess.SubprocessError as e:
            logger.error(f"Git command error: {e}")
            raise GitError(f"Git command error: {e}") from e
    
    def clone_repo(
        self,
        repo_url: str,
        target_path: str,
        branch: Optional[str] = None,
        depth: Optional[int] = None,
        bare: bool = False
    ) -> str:
        """
        Clone a git repository.
        
        Args:
            repo_url: Repository URL (https or ssh)
            target_path: Local path to clone into
            branch: Specific branch to clone (None for default)
            depth: Shallow clone depth (None for full clone)
            bare: Clone as bare repository
            
        Returns:
            Path to cloned repository
            
        Raises:
            GitCloneError: If clone fails
        """
        args = ['clone']
        
        if bare:
            args.append('--bare')
        
        if depth is not None:
            args.extend(['--depth', str(depth)])
        
        if branch:
            args.extend(['--branch', branch])
        
        args.extend([repo_url, target_path])
        
        try:
            logger.info(f"Cloning {repo_url} to {target_path}")
            self._run_git(args, check=True)
            
            # Configure git user in the cloned repo
            self._configure_user(target_path)
            
            logger.info(f"Successfully cloned to {target_path}")
            return target_path
            
        except GitError as e:
            raise GitCloneError(f"Failed to clone {repo_url}: {e}") from e
    
    def _configure_user(self, repo_path: str):
        """Configure git user in the repository."""
        try:
            self._run_git(
                ['config', 'user.name', self.config.user_name],
                cwd=repo_path,
                check=False
            )
            self._run_git(
                ['config', 'user.email', self.config.user_email],
                cwd=repo_path,
                check=False
            )
        except GitError:
            # Non-fatal, git may use global config
            pass
    
    def checkout_branch(
        self,
        repo_path: str,
        branch: str,
        create_from: Optional[str] = None,
        orphan: bool = False
    ) -> str:
        """
        Checkout a branch, optionally creating it.
        
        Args:
            repo_path: Path to repository
            branch: Branch name to checkout
            create_from: If provided, create new branch from this branch
            orphan: Create orphan branch
            
        Returns:
            Current branch name
            
        Raises:
            GitCheckoutError: If checkout fails
        """
        try:
            # First, fetch to ensure we have latest refs
            self._run_git(['fetch', '--all'], cwd=repo_path, check=False)
            
            if orphan:
                # Create orphan branch
                self._run_git(
                    ['checkout', '--orphan', branch],
                    cwd=repo_path
                )
            elif create_from:
                # Create and checkout new branch
                # First checkout the base branch
                self._run_git(
                    ['checkout', create_from],
                    cwd=repo_path,
                    check=False  # May already be on this branch
                )
                # Pull latest changes
                self._run_git(
                    ['pull', 'origin', create_from],
                    cwd=repo_path,
                    check=False
                )
                # Create and checkout new branch
                self._run_git(
                    ['checkout', '-b', branch],
                    cwd=repo_path
                )
            else:
                # Checkout existing branch
                self._run_git(['checkout', branch], cwd=repo_path)
            
            logger.info(f"Checked out branch {branch} in {repo_path}")
            return branch
            
        except GitError as e:
            raise GitCheckoutError(f"Failed to checkout branch {branch}: {e}") from e
    
    def get_current_branch(self, repo_path: str) -> str:
        """Get the current branch name."""
        result = self._run_git(
            ['rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=repo_path
        )
        return result.stdout.strip()
    
    def get_changed_files(self, repo_path: str) -> List[str]:
        """Get list of changed files (staged and unstaged)."""
        # Get staged files
        staged = self._run_git(
            ['diff', '--cached', '--name-only'],
            cwd=repo_path,
            check=False
        )
        
        # Get unstaged files
        unstaged = self._run_git(
            ['diff', '--name-only'],
            cwd=repo_path,
            check=False
        )
        
        # Get untracked files
        untracked = self._run_git(
            ['ls-files', '--others', '--exclude-standard'],
            cwd=repo_path,
            check=False
        )
        
        files = set()
        if staged.stdout:
            files.update(staged.stdout.strip().split('\n'))
        if unstaged.stdout:
            files.update(unstaged.stdout.strip().split('\n'))
        if untracked.stdout:
            files.update(untracked.stdout.strip().split('\n'))
        
        return [f for f in files if f]
    
    def has_changes(self, repo_path: str) -> bool:
        """Check if there are any changes in the working directory."""
        try:
            result = self._run_git(
                ['status', '--porcelain'],
                cwd=repo_path
            )
            return bool(result.stdout.strip())
        except GitError:
            return False
    
    def stage_all(self, repo_path: str):
        """Stage all changes in the repository."""
        self._run_git(['add', '-A'], cwd=repo_path)
        logger.debug(f"Staged all changes in {repo_path}")
    
    def commit_changes(
        self,
        repo_path: str,
        message: str,
        author: Optional[str] = None,
        date: Optional[str] = None,
        allow_empty: bool = False
    ) -> str:
        """
        Commit changes in the repository.
        
        Args:
            repo_path: Path to repository
            message: Commit message
            author: Optional author (Name <email> format)
            date: Optional commit date (ISO format)
            allow_empty: Allow empty commits
            
        Returns:
            Commit hash
            
        Raises:
            GitCommitError: If commit fails
        """
        try:
            # Stage all changes first
            self.stage_all(repo_path)
            
            # Check if there are changes (unless allowing empty)
            if not allow_empty and not self.has_changes(repo_path):
                logger.info("No changes to commit")
                return ""
            
            # Build commit command
            args = ['commit', '-m', message]
            
            if allow_empty:
                args.append('--allow-empty')
            
            if author:
                args.extend(['--author', author])
            
            if date:
                args.extend(['--date', date])
            
            # Run commit
            self._run_git(args, cwd=repo_path)
            
            # Get the commit hash
            result = self._run_git(
                ['rev-parse', 'HEAD'],
                cwd=repo_path
            )
            commit_hash = result.stdout.strip()
            
            logger.info(f"Created commit {commit_hash[:8]}: {message[:50]}")
            return commit_hash
            
        except GitError as e:
            raise GitCommitError(f"Failed to commit: {e}") from e
    
    def push_changes(
        self,
        repo_path: str,
        branch: Optional[str] = None,
        remote: str = 'origin',
        force: bool = False,
        set_upstream: bool = True
    ) -> Dict[str, Any]:
        """
        Push changes to remote.
        
        Args:
            repo_path: Path to repository
            branch: Branch to push (None for current)
            remote: Remote name
            force: Force push
            set_upstream: Set upstream tracking
            
        Returns:
            Dict with push results
            
        Raises:
            GitPushError: If push fails
        """
        try:
            # Get current branch if not specified
            if not branch:
                branch = self.get_current_branch(repo_path)
            
            # Build push command
            args = ['push']
            
            if force:
                args.append('--force')
            
            if set_upstream:
                args.extend(['--set-upstream', remote, branch])
            else:
                args.extend([remote, branch])
            
            # Run push
            result = self._run_git(args, cwd=repo_path)
            
            push_result = {
                'success': True,
                'remote': remote,
                'branch': branch,
                'output': result.stdout,
                'errors': result.stderr
            }
            
            logger.info(f"Pushed {branch} to {remote}")
            return push_result
            
        except GitError as e:
            raise GitPushError(f"Failed to push to {remote}/{branch}: {e}") from e
    
    def pull_changes(
        self,
        repo_path: str,
        branch: Optional[str] = None,
        remote: str = 'origin',
        rebase: bool = False
    ) -> Dict[str, Any]:
        """
        Pull changes from remote.
        
        Args:
            repo_path: Path to repository
            branch: Branch to pull (None for current)
            remote: Remote name
            rebase: Use rebase instead of merge
            
        Returns:
            Dict with pull results
        """
        try:
            args = ['pull']
            
            if rebase:
                args.append('--rebase')
            
            args.append(remote)
            
            if branch:
                args.append(branch)
            
            result = self._run_git(args, cwd=repo_path)
            
            return {
                'success': True,
                'output': result.stdout,
                'errors': result.stderr
            }
            
        except GitError as e:
            logger.error(f"Failed to pull: {e}")
            raise
    
    def get_remote_url(self, repo_path: str, remote: str = 'origin') -> Optional[str]:
        """Get the URL of a remote."""
        try:
            result = self._run_git(
                ['remote', 'get-url', remote],
                cwd=repo_path,
                check=False
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except GitError:
            return None
    
    def set_remote_url(
        self,
        repo_path: str,
        url: str,
        remote: str = 'origin'
    ):
        """Set the URL of a remote (create if doesn't exist)."""
        try:
            # Check if remote exists
            result = self._run_git(
                ['remote', 'get-url', remote],
                cwd=repo_path,
                check=False
            )
            
            if result.returncode == 0:
                # Remote exists, update URL
                self._run_git(
                    ['remote', 'set-url', remote, url],
                    cwd=repo_path
                )
            else:
                # Remote doesn't exist, add it
                self._run_git(
                    ['remote', 'add', remote, url],
                    cwd=repo_path
                )
            
            logger.info(f"Set remote {remote} to {url}")
            
        except GitError as e:
            logger.error(f"Failed to set remote URL: {e}")
            raise
    
    def create_pull_request_url(self, repo_path: str, branch: str) -> Optional[str]:
        """
        Generate a pull request URL for common git providers.
        
        Returns:
            PR creation URL or None if not supported
        """
        remote_url = self.get_remote_url(repo_path)
        if not remote_url:
            return None
        
        # Handle SSH URLs (git@github.com:user/repo.git)
        if remote_url.startswith('git@'):
            # SSH format: git@host:path/to/repo.git
            parts = remote_url[4:].split(':', 1)  # Remove 'git@' and split at first ':'
            if len(parts) == 2:
                host, repo_path_part = parts
                repo_path_part = '/' + repo_path_part.rstrip('/').replace('.git', '')
            else:
                return None
        else:
            # HTTPS format
            parsed = urlparse(remote_url)
            host = parsed.netloc
            repo_path_part = parsed.path.rstrip('/').replace('.git', '')
        
        # Generate PR URL based on host
        if 'github.com' in host:
            return f"https://github.com{repo_path_part}/pull/new/{branch}"
        elif 'gitlab.com' in host:
            return f"https://gitlab.com{repo_path_part}/merge_requests/new?merge_request[source_branch]={branch}"
        elif 'bitbucket.org' in host:
            return f"https://bitbucket.org{repo_path_part}/pull-requests/new?source={branch}"
        
        return None
    
    def reset_hard(self, repo_path: str, ref: str = 'HEAD'):
        """Hard reset to a reference (useful for cleanup)."""
        try:
            self._run_git(['reset', '--hard', ref], cwd=repo_path)
            logger.info(f"Hard reset {repo_path} to {ref}")
        except GitError as e:
            logger.error(f"Failed to reset: {e}")
            raise
    
    def clean_untracked(self, repo_path: str, force: bool = True):
        """Remove untracked files."""
        try:
            args = ['clean', '-fd']
            if force:
                args.append('-f')
            self._run_git(args, cwd=repo_path)
            logger.info(f"Cleaned untracked files in {repo_path}")
        except GitError as e:
            logger.error(f"Failed to clean: {e}")
            raise


# Convenience functions for simple use cases

def clone_and_setup(
    repo_url: str,
    target_path: str,
    branch: str = 'main'
) -> GitOperations:
    """
    Clone a repo and set it up for use.
    
    Returns:
        GitOperations instance configured for the repo
    """
    git_ops = GitOperations()
    git_ops.clone_repo(repo_url, target_path)
    git_ops.checkout_branch(target_path, branch)
    return git_ops

"""
Unit tests for Git Operations module.

Tests cover:
- Git configuration
- Repository cloning
- Branch operations
- Commit operations
- Push operations
- Error handling
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add project root and devclaw-runner src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from git_ops import (
    GitOperations,
    GitConfig,
    GitError,
    GitCloneError,
    GitCheckoutError,
    GitCommitError,
    GitPushError,
    clone_and_setup
)


@pytest.fixture
def git_config():
    """Create a git configuration for testing."""
    return GitConfig(
        user_name="Test User",
        user_email="test@example.com",
        default_branch="main"
    )


@pytest.fixture
def git_ops(git_config):
    """Create a GitOperations instance for testing."""
    return GitOperations(config=git_config)


@pytest.fixture
def temp_repo():
    """Create a temporary git repository."""
    repo_dir = tempfile.mkdtemp(prefix="git-test-")
    
    # Initialize git repo
    subprocess.run(['git', 'init'], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=repo_dir, capture_output=True, check=True)
    
    # Create initial commit
    test_file = Path(repo_dir) / "test.txt"
    test_file.write_text("initial content")
    subprocess.run(['git', 'add', '.'], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=repo_dir, capture_output=True, check=True)
    
    yield repo_dir
    
    # Cleanup
    import shutil
    shutil.rmtree(repo_dir)


class TestGitConfig:
    """Tests for GitConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = GitConfig()
        assert config.user_name == "DevClaw Runner"
        assert config.user_email == "devclaw@openclaw.local"
        assert config.default_branch == "main"
    
    def test_config_from_env(self, monkeypatch):
        """Test configuration from environment variables."""
        monkeypatch.setenv('DEVCLAW_GIT_USER_NAME', 'Env User')
        monkeypatch.setenv('DEVCLAW_GIT_USER_EMAIL', 'env@example.com')
        monkeypatch.setenv('DEVCLAW_GIT_DEFAULT_BRANCH', 'master')
        
        config = GitConfig.from_env()
        
        assert config.user_name == "Env User"
        assert config.user_email == "env@example.com"
        assert config.default_branch == "master"


class TestGitOperationsInit:
    """Tests for GitOperations initialization."""
    
    def test_init_with_config(self, git_config):
        """Test initialization with custom config."""
        ops = GitOperations(config=git_config)
        assert ops.config == git_config
        assert 'GIT_AUTHOR_NAME' in ops._env
        assert ops._env['GIT_AUTHOR_NAME'] == git_config.user_name
    
    def test_init_default_config(self):
        """Test initialization with default config."""
        ops = GitOperations()
        assert ops.config is not None
        assert ops.config.user_name == "DevClaw Runner"


class TestRunGit:
    """Tests for _run_git method."""
    
    def test_run_git_success(self, git_ops):
        """Test successful git command execution."""
        result = git_ops._run_git(['--version'], capture_output=True)
        
        assert result.returncode == 0
        assert 'git version' in result.stdout.lower()
    
    def test_run_git_failure(self, git_ops):
        """Test git command failure raises error."""
        with pytest.raises(GitError) as exc_info:
            git_ops._run_git(['invalid-command'])
        
        assert 'Git command failed' in str(exc_info.value)
    
    def test_run_git_no_check(self, git_ops):
        """Test git command with check=False doesn't raise."""
        result = git_ops._run_git(['invalid-command'], check=False)
        
        assert result.returncode != 0
    
    def test_run_git_timeout(self, git_ops):
        """Test git command timeout."""
        # This is hard to test reliably, but we can verify the parameter is accepted
        result = git_ops._run_git(['--version'], timeout=10)
        assert result.returncode == 0


class TestCloneRepo:
    """Tests for clone_repo method."""
    
    @patch('git_ops.subprocess.run')
    def test_clone_repo_success(self, mock_run, git_ops):
        """Test successful repository cloning."""
        mock_run.return_value = Mock(returncode=0, stdout='', stderr='')
        
        target = "/tmp/test-clone"
        result = git_ops.clone_repo("https://github.com/test/repo.git", target)
        
        assert result == target
        mock_run.assert_called()
        
        # Verify git clone was called
        call_args = mock_run.call_args_list[0]
        assert 'clone' in call_args[0][0]
    
    @patch('git_ops.subprocess.run')
    def test_clone_repo_with_branch(self, mock_run, git_ops):
        """Test cloning specific branch."""
        mock_run.return_value = Mock(returncode=0, stdout='', stderr='')
        
        git_ops.clone_repo(
            "https://github.com/test/repo.git",
            "/tmp/test-clone",
            branch="develop"
        )
        
        call_args = mock_run.call_args_list[0][0][0]
        assert '--branch' in call_args
        assert 'develop' in call_args
    
    @patch('git_ops.subprocess.run')
    def test_clone_repo_shallow(self, mock_run, git_ops):
        """Test shallow clone."""
        mock_run.return_value = Mock(returncode=0, stdout='', stderr='')
        
        git_ops.clone_repo(
            "https://github.com/test/repo.git",
            "/tmp/test-clone",
            depth=1
        )
        
        call_args = mock_run.call_args_list[0][0][0]
        assert '--depth' in call_args
        assert '1' in call_args
    
    @patch('git_ops.subprocess.run')
    def test_clone_repo_failure(self, mock_run, git_ops):
        """Test clone failure raises exception."""
        mock_run.return_value = Mock(
            returncode=128,
            stdout='',
            stderr='Repository not found'
        )
        
        with pytest.raises(GitCloneError) as exc_info:
            git_ops.clone_repo("https://github.com/test/nonexistent.git", "/tmp/test-clone")
        
        assert 'Failed to clone' in str(exc_info.value)


class TestCheckoutBranch:
    """Tests for checkout_branch method."""
    
    def test_checkout_existing_branch(self, git_ops, temp_repo):
        """Test checking out existing branch."""
        # Create a branch first
        subprocess.run(
            ['git', 'checkout', '-b', 'feature-branch'],
            cwd=temp_repo,
            capture_output=True,
            check=True
        )
        
        # Go back to master (default branch in test repo)
        subprocess.run(
            ['git', 'checkout', 'master'],
            cwd=temp_repo,
            capture_output=True,
            check=True
        )
        
        # Test checkout
        result = git_ops.checkout_branch(temp_repo, 'feature-branch')
        
        assert result == 'feature-branch'
        
        # Verify we're on the branch
        current = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True
        )
        assert current.stdout.strip() == 'feature-branch'
    
    def test_create_new_branch(self, git_ops, temp_repo):
        """Test creating and checking out new branch."""
        result = git_ops.checkout_branch(temp_repo, 'new-feature', create_from='main')
        
        assert result == 'new-feature'
        
        # Verify branch exists
        branches = subprocess.run(
            ['git', 'branch'],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True
        )
        assert 'new-feature' in branches.stdout
    
    def test_checkout_failure(self, git_ops, temp_repo):
        """Test checkout of non-existent branch."""
        with pytest.raises(GitCheckoutError):
            git_ops.checkout_branch(temp_repo, 'non-existent-branch')


class TestCommitChanges:
    """Tests for commit_changes method."""
    
    def test_commit_changes_success(self, git_ops, temp_repo):
        """Test successful commit."""
        # Make a change
        test_file = Path(temp_repo) / "new_file.txt"
        test_file.write_text("new content")
        
        # Commit
        commit_hash = git_ops.commit_changes(temp_repo, "Test commit message")
        
        assert commit_hash is not None
        assert len(commit_hash) == 40  # Full SHA
        
        # Verify commit exists
        log = subprocess.run(
            ['git', 'log', '-1', '--oneline'],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True
        )
        assert 'Test commit message' in log.stdout
    
    def test_commit_no_changes(self, git_ops, temp_repo):
        """Test commit with no changes."""
        result = git_ops.commit_changes(temp_repo, "No changes")
        
        assert result == ""  # No commit made
    
    def test_commit_allow_empty(self, git_ops, temp_repo):
        """Test allow empty commit."""
        commit_hash = git_ops.commit_changes(
            temp_repo,
            "Empty commit",
            allow_empty=True
        )
        
        assert commit_hash is not None
        assert len(commit_hash) == 40
    
    def test_commit_with_author(self, git_ops, temp_repo):
        """Test commit with custom author."""
        test_file = Path(temp_repo) / "author_test.txt"
        test_file.write_text("content")
        
        commit_hash = git_ops.commit_changes(
            temp_repo,
            "Author test",
            author="Custom Author <custom@example.com>"
        )
        
        # Verify author
        author_info = subprocess.run(
            ['git', 'log', '-1', '--format=%an <%ae>'],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True
        )
        assert "Custom Author" in author_info.stdout


class TestPushChanges:
    """Tests for push_changes method."""
    
    @patch('git_ops.subprocess.run')
    def test_push_changes_success(self, mock_run, git_ops):
        """Test successful push."""
        mock_run.return_value = Mock(returncode=0, stdout='Everything up-to-date', stderr='')
        
        result = git_ops.push_changes('/fake/repo', 'main')
        
        assert result['success'] is True
        assert result['branch'] == 'main'
    
    @patch('git_ops.subprocess.run')
    def test_push_changes_with_force(self, mock_run, git_ops):
        """Test force push."""
        mock_run.return_value = Mock(returncode=0, stdout='', stderr='')
        
        git_ops.push_changes('/fake/repo', 'main', force=True)
        
        call_args = mock_run.call_args[0][0]
        assert '--force' in call_args
    
    @patch('git_ops.subprocess.run')
    def test_push_changes_failure(self, mock_run, git_ops):
        """Test push failure."""
        mock_run.return_value = Mock(
            returncode=1,
            stdout='',
            stderr='rejected: non-fast-forward'
        )
        
        with pytest.raises(GitPushError) as exc_info:
            git_ops.push_changes('/fake/repo', 'main')
        
        assert 'Failed to push' in str(exc_info.value)


class TestGetChangedFiles:
    """Tests for get_changed_files method."""
    
    def test_get_changed_files_modified(self, git_ops, temp_repo):
        """Test getting modified files."""
        # Modify a file
        test_file = Path(temp_repo) / "test.txt"
        test_file.write_text("modified content")
        
        files = git_ops.get_changed_files(temp_repo)
        
        assert 'test.txt' in files
    
    def test_get_changed_files_new(self, git_ops, temp_repo):
        """Test getting new untracked files."""
        # Create a new file
        test_file = Path(temp_repo) / "new_file.txt"
        test_file.write_text("new content")
        
        files = git_ops.get_changed_files(temp_repo)
        
        assert 'new_file.txt' in files
    
    def test_get_changed_files_staged(self, git_ops, temp_repo):
        """Test getting staged files."""
        # Create and stage a file
        test_file = Path(temp_repo) / "staged.txt"
        test_file.write_text("staged content")
        subprocess.run(['git', 'add', '.'], cwd=temp_repo, capture_output=True, check=True)
        
        files = git_ops.get_changed_files(temp_repo)
        
        assert 'staged.txt' in files
    
    def test_get_changed_files_none(self, git_ops, temp_repo):
        """Test when no files changed."""
        files = git_ops.get_changed_files(temp_repo)
        
        assert files == []


class TestHasChanges:
    """Tests for has_changes method."""
    
    def test_has_changes_true(self, git_ops, temp_repo):
        """Test detecting changes."""
        # Create a new file
        test_file = Path(temp_repo) / "change_test.txt"
        test_file.write_text("content")
        
        assert git_ops.has_changes(temp_repo) is True
    
    def test_has_changes_false(self, git_ops, temp_repo):
        """Test no changes detected."""
        assert git_ops.has_changes(temp_repo) is False


class TestStageAll:
    """Tests for stage_all method."""
    
    def test_stage_all(self, git_ops, temp_repo):
        """Test staging all changes."""
        # Create multiple files
        (Path(temp_repo) / "file1.txt").write_text("content1")
        (Path(temp_repo) / "file2.txt").write_text("content2")
        
        git_ops.stage_all(temp_repo)
        
        # Verify files are staged
        staged = subprocess.run(
            ['git', 'diff', '--cached', '--name-only'],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True
        )
        assert 'file1.txt' in staged.stdout
        assert 'file2.txt' in staged.stdout


class TestGetRemoteUrl:
    """Tests for get_remote_url method."""
    
    def test_get_remote_url(self, git_ops, temp_repo):
        """Test getting remote URL."""
        # Add a remote
        subprocess.run(
            ['git', 'remote', 'add', 'origin', 'https://github.com/test/repo.git'],
            cwd=temp_repo,
            capture_output=True,
            check=True
        )
        
        url = git_ops.get_remote_url(temp_repo)
        
        assert url == 'https://github.com/test/repo.git'
    
    def test_get_remote_url_none(self, git_ops, temp_repo):
        """Test getting remote URL when no remote exists."""
        url = git_ops.get_remote_url(temp_repo)
        
        assert url is None


class TestSetRemoteUrl:
    """Tests for set_remote_url method."""
    
    def test_set_remote_url_new(self, git_ops, temp_repo):
        """Test setting remote URL for new remote."""
        git_ops.set_remote_url(temp_repo, 'https://github.com/new/repo.git', 'origin')
        
        url = git_ops.get_remote_url(temp_repo)
        assert url == 'https://github.com/new/repo.git'
    
    def test_set_remote_url_update(self, git_ops, temp_repo):
        """Test updating existing remote URL."""
        # Add initial remote
        subprocess.run(
            ['git', 'remote', 'add', 'origin', 'https://github.com/old/repo.git'],
            cwd=temp_repo,
            capture_output=True,
            check=True
        )
        
        # Update URL
        git_ops.set_remote_url(temp_repo, 'https://github.com/new/repo.git', 'origin')
        
        url = git_ops.get_remote_url(temp_repo)
        assert url == 'https://github.com/new/repo.git'


class TestCreatePullRequestUrl:
    """Tests for create_pull_request_url method."""
    
    def test_github_pr_url(self, git_ops):
        """Test GitHub PR URL generation."""
        with patch.object(git_ops, 'get_remote_url', return_value='https://github.com/user/repo.git'):
            url = git_ops.create_pull_request_url('/fake/repo', 'feature-branch')
        
        assert 'github.com/user/repo' in url
        assert 'pull/new' in url
        assert 'feature-branch' in url
    
    def test_github_ssh_url(self, git_ops):
        """Test GitHub PR URL from SSH remote."""
        with patch.object(git_ops, 'get_remote_url', return_value='git@github.com:user/repo.git'):
            url = git_ops.create_pull_request_url('/fake/repo', 'feature-branch')
        
        assert 'github.com/user/repo' in url
    
    def test_gitlab_pr_url(self, git_ops):
        """Test GitLab MR URL generation."""
        with patch.object(git_ops, 'get_remote_url', return_value='https://gitlab.com/user/repo.git'):
            url = git_ops.create_pull_request_url('/fake/repo', 'feature-branch')
        
        assert 'gitlab.com/user/repo' in url
        assert 'merge_requests/new' in url
    
    def test_bitbucket_pr_url(self, git_ops):
        """Test Bitbucket PR URL generation."""
        with patch.object(git_ops, 'get_remote_url', return_value='https://bitbucket.org/user/repo.git'):
            url = git_ops.create_pull_request_url('/fake/repo', 'feature-branch')
        
        assert 'bitbucket.org/user/repo' in url
        assert 'pull-requests/new' in url
    
    def test_unknown_provider(self, git_ops):
        """Test PR URL for unknown provider."""
        with patch.object(git_ops, 'get_remote_url', return_value='https://unknown.com/repo.git'):
            url = git_ops.create_pull_request_url('/fake/repo', 'feature-branch')
        
        assert url is None
    
    def test_no_remote(self, git_ops):
        """Test PR URL when no remote exists."""
        with patch.object(git_ops, 'get_remote_url', return_value=None):
            url = git_ops.create_pull_request_url('/fake/repo', 'feature-branch')
        
        assert url is None


class TestResetHard:
    """Tests for reset_hard method."""
    
    def test_reset_hard(self, git_ops, temp_repo):
        """Test hard reset."""
        # Make a change
        test_file = Path(temp_repo) / "test.txt"
        original_content = test_file.read_text()
        test_file.write_text("changed content")
        
        # Reset
        git_ops.reset_hard(temp_repo)
        
        # Verify reset
        content = test_file.read_text()
        assert content == original_content


class TestCleanUntracked:
    """Tests for clean_untracked method."""
    
    def test_clean_untracked(self, git_ops, temp_repo):
        """Test cleaning untracked files."""
        # Create untracked files
        (Path(temp_repo) / "untracked.txt").write_text("content")
        (Path(temp_repo) / "untracked_dir").mkdir()
        (Path(temp_repo) / "untracked_dir" / "file.txt").write_text("nested")
        
        git_ops.clean_untracked(temp_repo)
        
        # Verify cleaned
        assert not (Path(temp_repo) / "untracked.txt").exists()
        assert not (Path(temp_repo) / "untracked_dir").exists()


class TestCloneAndSetup:
    """Tests for clone_and_setup convenience function."""
    
    @patch('git_ops.GitOperations')
    @patch('git_ops.GitConfig')
    def test_clone_and_setup(self, mock_config_class, mock_ops_class):
        """Test clone_and_setup convenience function."""
        mock_ops = MagicMock()
        mock_ops_class.return_value = mock_ops
        
        result = clone_and_setup('https://github.com/test/repo.git', '/tmp/test', 'develop')
        
        mock_ops.clone_repo.assert_called_once_with('https://github.com/test/repo.git', '/tmp/test')
        mock_ops.checkout_branch.assert_called_once_with('/tmp/test', 'develop')
        assert result == mock_ops

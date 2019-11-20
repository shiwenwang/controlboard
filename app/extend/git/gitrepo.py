from git import Repo
from git.repo.fun import is_git_dir
import os


class GitRepo(object):
    def __init__(self):  
        self.repo = None
        self.origin = None

    def git_exists(self, local_dir):
        """``true``, the local_dir is a git working tree directory.
        
        Arguments:
            local_dir {str} -- local repo dir
        """
        git_path = self.abspath(os.path.join(local_dir, '.git'))
        return is_git_dir(git_path)

    def is_dirty(self):
        """
        ``true``, the repository is considered dirty.
        if there is any untracked or unstaged file, `dirty` is ``true``.
        
        """
        return self.repo.is_dirty(untracked_files=True)

    def clone(self, remote_repo_url, local_repo_dir):
        """Clone a remote repo from `remote_repo_url` to `local_repo_dir`.
        
        Arguments:
            remote_repo_url {str} -- url for remote git repo
            local_repo_dir {str} -- local repo dir
        """     
        self.repo = Repo.clone_from(remote_repo_url, self.abspath(local_repo_dir))
        self.origin = self.repo.remotes.origin
    
    def open(self, local_repo_dir):
        """Connect an existed git repo.
        
        Arguments:
            local_repo_dir {str} -- local repo dir
        """
        self.repo = Repo(self.abspath(local_repo_dir))
        self.origin = self.repo.remotes.origin

    def commit_with_added(self, commit_despec):
        """Make a force commit.
        
        Arguments:
            commit_despec {str} -- the description of commit
        """
        if self.is_dirty():
            untracked_files = self.repo.untracked_files
            self.repo.index.add(untracked_files)
            self.repo.index.commit(commit_despec)

    def commit_with_remove(self, file):
        git = self.repo.git
        git.execute(f'git rm {file}')

    def easy_push(self):
        self.pull()
        self.push()

    def push(self):
        self.origin.push()

    def pull(self):
        self.origin.pull()

    @staticmethod
    def abspath(path):
        return os.path.abspath(path)


def git_init(git_path, username):
    repo = GitRepo()
    if not repo.git_exists(git_path):
        repo.clone(f'http://bitbucket.goldwind.com.cn/scm/~36719/{username}.git', git_path)
        # .gitignore
        gitignore_path = os.path.join(git_path, '.gitignore')
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, 'w') as f:
                f.write('*.xlsx\n*.xlsx\n*.db')
        repo.commit_with_added('Initial Commit.')
        repo.push()


def git_commit_push(git_path, commit_str):
    repo = GitRepo()
    repo.open(git_path)
    if repo.is_dirty():
        repo.commit_with_added(commit_str)
        repo.easy_push()


def git_remove_push(git_path, filelist):
    repo = GitRepo()
    repo.open(git_path)
    for file in filelist:
        repo.commit_with_remove(file)

    repo.repo.git.execute(f'git commit -m "Deleted"')
    repo.easy_push()

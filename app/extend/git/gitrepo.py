from git import Repo
from git.repo.fun import is_git_dir
from git.exc import GitCommandError
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
            # untracked_files = self.repo.untracked_files  # 不包含已删除的文件
            # self.repo.index.add(untracked_files)
            # self.repo.index.commit(commit_despec)
            git = self.repo.git
            git.execute(f'git add .')  # 可以将未添加的和已删除的都提交到Changes to be committed状态
            git.execute(f'git commit -m "{commit_despec}"')

    def remove(self, file):
        git = self.repo.git
        git.execute(f'git rm {file}')

    def easy_push(self):
        try:
            self.pull()
        except GitCommandError:
            git = self.repo.git
            git.execute('git reset --hard FETCH_HEAD')  # 解决冲突
            self.origin.pull()
        self.push()

    def push(self):
        self.origin.push()

    def pull(self):
        self.origin.pull()

    @staticmethod
    def abspath(path):
        return os.path.abspath(path)


def git_init(git_path, username, isgitted, newfolder=None):
    repo = GitRepo()
    if not repo.git_exists(git_path):
        repo.clone(os.getenv('REMOTE_GIT', 'http://bitbucket.goldwind.com.cn/scm/~36719/controller-files-dev.git'), git_path)
        # .gitignore
        gitignore_path = os.path.join(git_path, '.gitignore')
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, 'w') as f:
                f.write('*\n!*/\n*/*\n!.gitignore\n!*.dll\n!*.xml\n!*.ini\n!*.$pj\n!*.prj\n!README.txt')
                if not isgitted and newfolder is not None:
                    f.write(f'\n{newfolder}/')
        repo.commit_with_added('Initial Commit.')
        repo.push()


def git_commit_push(git_path, commit_str, wait_push=False):
    repo = GitRepo()
    repo.open(git_path)
    if repo.is_dirty():
        repo.commit_with_added(commit_str)
    if not wait_push:
        repo.easy_push()


def git_remove_push(git_path, filelist, commit_str):
    repo = GitRepo()
    repo.open(git_path)
    for file in filelist:
        repo.remove(file)

    repo.commit_with_added(commit_str)
    repo.easy_push()


def git_exists(folder):
    repo = GitRepo()
    return repo.git_exists(folder)

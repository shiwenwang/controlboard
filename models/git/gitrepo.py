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
        

if __name__ == "__main__":
    import os
    import time
    from multiprocessing import Process, current_process, Pool

    remote_repo = 'http://bitbucket.goldwind.com.cn/scm/~36719/controller-files.git'
    user1_repo_dir = os.path.abspath('./user111')
    user2_repo_dir = os.path.abspath('./user222')
    user3_repo_dir = os.path.abspath('./user333')
    user4_repo_dir = os.path.abspath('./user444')

    user1_repo = GitRepo()
    user2_repo = GitRepo()
    user3_repo = GitRepo()
    user4_repo = GitRepo()
    
    pool = Pool(4)
    pool.apply_async(user1_repo.clone, args=(remote_repo, user1_repo_dir))
    pool.apply_async(user2_repo.clone, args=(remote_repo, user2_repo_dir))
    pool.apply_async(user3_repo.clone, args=(remote_repo, user3_repo_dir))
    pool.apply_async(user4_repo.clone, args=(remote_repo, user4_repo_dir))

    pool.close()
    pool.join()

    print('main')

    user1_repo.commit_with_added('user1 commit')
    user2_repo.commit_with_added('user2 commit')

    user1_repo.easy_push()
    user2_repo.easy_push()


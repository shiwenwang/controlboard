from bladed import Bladed
from mode import Mode
import subprocess
from subprocess import Popen, PIPE, STDOUT
from multiprocessing import Process
import os
import sys
import chardet
import logging


def info(title):
    print(title)
    print('module name:', __name__)
    print('parent process:', os.getppid())
    print('process id:', os.getpid())

def supervisor(bladed, run_dir):
    bladed.campbell(run_dir)    
    mode = Mode(run_dir)
    tower_mode_1 = mode.get_freq('Tower mode 1')
    print(tower_mode_1)
    

if __name__ == "__main__":
    info('main process.')

    bladed_file_path = os.path.abspath('./GW150P2800TS140_700BGW73.2_V2.$PJ')
    bladed = Bladed(bladed_file_path)
    bladed.modify_v47()
    # run_dir = os.path.abspath("./run4.6-raw")
    
    # p_supervisor = Process(target=supervisor, args=(bladed, run_dir,))
    # p_supervisor.start()
    print("主进程结束.")

'''
@Descripttion: 仿真时序读取
@version: 
@Author: wangshiwen@36719
@Date: 2019-12-24 10:39:59
@LastEditors  : wangshiwen@36719
@LastEditTime : 2019-12-24 11:21:46
'''

import os


class SimData():
    def __init__(self, run_dir):
        self.root = os.path.abspath(run_dir)

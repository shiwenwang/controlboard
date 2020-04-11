'''
@Descripttion:
@version:
@Author: wangshiwen@36719
@Date: 2019-12-03 09:45:15
@LastEditors: wangshiwen@36719
@LastEditTime: 2020-02-13 10:19:01
'''
from bladed import Bladed
from mode import Mode
from multiprocessing import Process
import os
import pytest


class TestBladed:
    def __init__(self, path):
        self.ver, self.path = path
        self.bladed = Bladed(self.path)

    def test_version(self):
        assert self.ver == self.bladed.version

    def test_query(self):
        assert ('RHO', '1.225') == self.bladed.query('RHO', number_only=True)
        assert ('RHO', '1.225') == self.bladed.query('RHO', number_only=False)
        assert ('PROJNAME', 'GW130P25BTG90_802KsBSinoma63.5A_V10_HNlingnan') == self.bladed.query('PROJNAME', number_only=False)
        assert None == self.bladed.query('PROJNAME', number_only=True)
        assert None == self.bladed.query('FOO', number_only=True)
        assert None == self.bladed.query('FOO', number_only=False)

    def test_set(self):
        pass



def info(title):
    print(title)
    print('module name:', __name__)
    print('parent process:', os.getppid())
    print('process id:', os.getpid())


def supervisor(_bladed, _run_dir):
    mode_map = {
        '3.82': 'Tower side-side mode 1',
        '4.3': 'Tower mode 1',
        '4.6': 'Tower mode 1',
        '4.7': 'Tower 1st side-side mode',
    }
    # _bladed.solo_run(_run_dir, dll_path, xml_path)
    # _bladed.campbell(_run_dir)
    mode = Mode(_run_dir)
    tower_mode_1 = mode.get_freq(mode_map[_bladed.version])
    print(tower_mode_1)


if __name__ == "__main__":
    info('main process.')

    bladed_file_path = os.path.abspath('./v3.82.$PJ')
    # dll_path = os.path.abspath('./042_001/GW140P2500TG90_1191_BSinoma68.6B_CFII_V6.01.01.dll')
    # xml_path = os.path.abspath('./042_001/GW140P2500TG90_1191_BSinoma68.6B_CFII_V6.01.01_huairenyiqi_D2-DLC042_082.xml')
    bladed = Bladed(bladed_file_path)

    # bladed.modify_v47()
    run_dir = os.path.abspath("./v3.82_run")

    p_supervisor = Process(target=supervisor, args=(bladed, run_dir))
    p_supervisor.start()
    print("主进程结束.")

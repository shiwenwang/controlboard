from bladed import Bladed
from mode import Mode
from multiprocessing import Process
import os


def info(title):
    print(title)
    print('module name:', __name__)
    print('parent process:', os.getppid())
    print('process id:', os.getpid())


def supervisor(_bladed, _run_dir, dll_path, xml_path):
    _bladed.solo_run(_run_dir, dll_path, xml_path)
    # mode = Mode(_run_dir)
    # tower_mode_1 = mode.get_freq('Tower mode 1')
    # print(tower_mode_1)
    

if __name__ == "__main__":
    info('main process.')

    bladed_file_path = os.path.abspath('./042_001/042_001.$PJ')
    dll_path = os.path.abspath('./042_001/GW140P2500TG90_1191_BSinoma68.6B_CFII_V6.01.01.dll')
    xml_path = os.path.abspath('./042_001/GW140P2500TG90_1191_BSinoma68.6B_CFII_V6.01.01_huairenyiqi_D2-DLC042_082.xml')
    bladed = Bladed(bladed_file_path)

    # bladed.modify_v47()
    run_dir = os.path.abspath("./042_001/run")

    p_supervisor = Process(target=supervisor, args=(bladed, run_dir, dll_path, xml_path))
    p_supervisor.start()
    print("主进程结束.")

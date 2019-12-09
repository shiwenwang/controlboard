import os
import re


class Mode():
    def __init__(self, run_dir):
        """[summary]
        
        Arguments:
            run_dir {[type]} -- [计算路径，结果文件在此]
        """
        self._dir = run_dir

    def get_mode(self, mode_name):
        cm_path = os.path.abspath(os.path.join(self._dir, 'lin1.$CM'))
        with open(cm_path, 'r') as f:
            data = f.read()
        m = re.findall(r"OMEGA[\t ]*(\S+)\nFREQ[\t ]*(\S+)\nDAMP[\t ]*(\S+)\nLABEL[\t ]*?'%s" % mode_name, data)
        if not m:
            raise Exception(f'没找到"{mode_name}", 请检查模态名称是否正确。')
        result_list = list(zip(*m))
        result = {'OMEGA': result_list[0], 'FREQ': result_list[1], 'DAMP': result_list[2]}

        return result

    def get_freq(self, mode_name, only_mean_value=True):
        mode = self.get_mode(mode_name)
        freq_lst = [float(d) for d in mode['FREQ']]
        if only_mean_value:
            freq_mean = sum(freq_lst)/len(freq_lst)
            return float('{:f}'.format(freq_mean))
        return freq_lst

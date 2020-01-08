'''
@Descripttion: 
@version: 
@Author: wangshiwen@36719
@Date: 2019-12-06 17:29:24
@LastEditors  : wangshiwen@36719
@LastEditTime : 2020-01-06 18:00:25
'''
import os
import re
import logging


class Mode():
    def __init__(self, run_dir):
        """[summary]
        
        Arguments:
            run_dir {[type]} -- [计算路径，结果文件在此]
        """
        self._dir = run_dir
        self.mode_names = self.get_names()

    def get_names(self):
        f_p = os.path.abspath(os.path.join(self._dir, 'lin1.%02'))
        
        try:
            with open(f_p, 'r') as f:
                content = f.read()

            m = re.search(r'^AXITICK[\t ]+(.*)$', content, re.MULTILINE)        
            names = [] if m is None else m.group(1).replace("' '", ',').replace("'", '').split(',')
            names = [name for name in names if 'Blade' in name[:5] or 'Tower' in name[:5]] if names else names
        except :
            names = []
            logging.warning('读取 lin1.%02 文件失败！')                
            
        return names
    
    def get_modes(self):
        modes = {"freqs":[], "damps": []}
        for name in self.mode_names:
            modes['freqs'].append(self.get_freq(name))
            modes['damps'].append(self.get_damp(name))
        
        return modes

    def get_mode(self, mode_name):
        cm_path = os.path.abspath(os.path.join(self._dir, 'lin1.$CM'))
        try:
            with open(cm_path, 'rb') as f:
                data_bytes = f.read()
        except :
            logging.warning('读取 lin1.$CM 文件失败！')
        data = data_bytes.decode('utf-8', 'ignore').replace('\r','')
        m = re.findall(r"OMEGA[\t ]*(\S+)\nFREQ[\t ]*(\S+)\nDAMP[\t ]*(\S+)\nLABEL[\t ]*?'%s" % mode_name, data)
        if not m:
            logging.warning(f'没找到"{mode_name}", 请检查模态名称是否正确。')
            return {'OMEGA': "", 'FREQ': "", 'DAMP': ""}
            
        result_list = list(zip(*m))
        result = {'OMEGA': result_list[0], 'FREQ': result_list[1], 'DAMP': result_list[2]}

        return result

    def get_freq(self, mode_name, only_mean_value=True):
        mode = self.get_mode(mode_name)
        freqs = [float(d) for d in mode['FREQ']]
        if only_mean_value:
            freq_mean = sum(freqs)/len(freqs) if freqs else 0
            return '{:f}'.format(freq_mean)
        return freqs
    
    def get_damp(self, mode_name, only_mean_value=True):
        mode = self.get_mode(mode_name)
        damps = [float(d) for d in mode['DAMP'] if self.is_number(d) if self.is_number(d)]
        if only_mean_value:
            damp_mean = sum(damps)/len(damps) if damps else 0
            return '{:f}'.format(damp_mean)
        return damps

    @staticmethod
    def is_number(s):
        try:
            float(s)
            return True
        except ValueError:
            pass
    
        try:
            import unicodedata
            unicodedata.numeric(s)
            return True
        except (TypeError, ValueError):
            pass
    
        return False
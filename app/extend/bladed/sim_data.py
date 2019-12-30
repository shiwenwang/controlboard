'''
@Descripttion: 
@version: 
@Author: wangshiwen@36719
@Date: 2019-12-24 10:39:59
@LastEditors  : wangshiwen@36719
@LastEditTime : 2019-12-27 18:01:02
'''

import os
import re
import numpy as np
import pandas as pd


class SimData:
    def __init__(self, run_dir):
        self.root = os.path.abspath(run_dir)
        self.__patterns = self.__set_pattern()

    @staticmethod
    def __set_pattern():
        """ 设置并提前编译要查找字段的正则表达式模板

        Returns:
            [dictionary] -- 每个字段对应的正则字符串
        """
        search_item = {
            'binary_file': 'FILE',  # 当前变量组对应的时序文件 <str>
            'bytes_size': 'RECL',  # 时序文件每个数据存储所占用的字节数 <int>
            'group': 'GENLAB',  # 当前变量组名 <str>
            'data_dimension': 'NDIMENS',  # 当前变量组中的数据维度（2维或3维）<int>
            # 当前变量组中各维度的长度(变量个数) [len(y_var), len(z_var), len(x_var)] <list>
            'data_shape': 'DIMENS',
            'y_var': 'VARIAB',  # 当前变量组中所有的变量，定为y轴 <list>
            'y_unit': 'VARUNIT',  # 当前变量组所有的变量的默认单位 <list>
            'xz_var': 'AXISLAB',  # 当前变量组中的x轴和z轴变量， 如果不存在z轴，列表长度为1 <list>
            'xz_unit': 'AXIUNIT',  # 当前变量组中的x轴和z轴变量的默认单位，与'xz_var'对应 <list>
            'xz_meth': 'AXIMETH',  # 可以理解为当前变量组中的x轴和z轴标识，与'xz_var'对应， '2'表示x轴， '3'表示z轴 <list>
            'z_val': 'AXIVAL',  # 当前变量组中z轴变量的数值, 可能为空，z多见于塔架和叶片截面、静态功率曲线中的桨距角范围 <list> or <str>
            'x_min': 'MIN',  # 当前变量组中x轴变量的起始数值 <float>
            'x_step': 'STEP',  # 当前变量组中x轴变量的步进值 <float>
        }
        ptns = {k: re.compile(r'^%s[\t ]+(.*)$' % v, re.M)
                for k, v in search_item.items()}
        return ptns

    def match_value(self, content, param):
        """匹配单个字段对应的值

        Arguments:
            content {str} -- 文件的文本字符串
            param {str} -- 字段名

        Returns:
            [type] -- [description]
        """
        m = self.patterns[param].findall(content)
        if m is None:
            return m

        raw_to_fine = {
            'binary_file': lambda m: m[0],
            'bytes_size': lambda m: eval(f'np.float{int(m[0]) * 8}'),
            'data_dimension': lambda m: int(m[0]),
            'data_shape': lambda m: [int(s) for s in m[0].split()],
            'group': lambda m: eval(m[0]),
            'y_var': lambda m: m[0].replace("' '", ',').replace("'", '').split(','),
            'y_unit': lambda m: m[0].split(),
            'xz_var': lambda m: [eval(v) for v in m],
            'xz_unit': lambda m: m,
            'xz_meth': lambda m: [int(s) for s in m],
            'z_val': lambda m: (m[0].split() if len(m[0].split()) > 1 else m[0]) if m else m,
            'x_min': lambda m: float(m[0]),
            'x_step': lambda m: float(m[0])
        }

        return raw_to_fine[param](m)

    def find_values(self, content, *args):
        """对所有感兴趣的字段执行match_value函数

        Arguments:
            content {str} -- 文件的文本字符串

        Returns:
            [dictionary] -- 见all_vars()
        """
        values = {arg: self.match_value(content, arg) for arg in args}
        return values

    @property
    def patterns(self):
        return self.__patterns

    def all_sims(self, with_vars=True):
        """获取当前目录下所有的仿真任务
        with_vars == True : 将仿真任务涉及到的变量组信息附加到任务名上

        Returns:
            [list] -- 仿真任务列表
        """
        sims = [os.path.splitext(item)[0] for item in os.listdir(self.root)
                if os.path.isfile(os.path.join(self.root, item)) and '.$PJ' in item]

        if with_vars:
            sims_with_vars = {sim: self.all_vars(sim) for sim in sims}
            return sims_with_vars

        return sims

    def all_vars(self, sim):
        """从单次仿真计算的结果中获取所有变量组名和变量名

        Arguments:
            sim {str} -- 仿真计算的文件名

        Returns:
            [dictionary] -- {变量组名：{
                对应的二进制文件：文件名，
                该组所有变量名：变量名列表，
                数据的维度：维度值（2或3），
                每一维度的数据长度：列表
            }}
        """
        var_files = [f for f in os.listdir(self.root) if f'{sim}.%' in f]
        vars = {}

        for vf in var_files:
            with open(os.path.join(self.root, vf), 'r') as f:
                content = f.read()
                values = self.find_values(
                    content, *tuple(self.__patterns.keys()))
                values['x_series'] = np.arange(
                    values['x_min'], values['x_min'] + values['x_step']*values['data_shape'][-1], values['x_step']).tolist()

            vars.update({values.pop('group'): values})

        return vars

    def get_data(self, sims_with_vars, sim, group):
        """根据仿真任务名和变量组名读取仿真时序（一个时序文件对应一个变量组）

        Arguments:
            sims_with_vars {dictionary} -- run_dir 目录下的所有的仿真任务及各任务的信息
            sim {string} -- 仿真任务名
            var {string} -- 变量组名
        """
        group_info = sims_with_vars[sim][group]
        group_data_raw = np.fromfile(os.path.join(
            self.root, group_info['binary_file']), dtype=group_info['bytes_size'])

        group_data_fine = group_data_raw.reshape(group_info['data_shape'], order='F')

        x_data = np.array(group_info['x_series']).reshape(1, len(group_info['x_series']))
        y_varname = group_info['y_var']
        x_varname = group_info['xz_var']

        if 2 == group_info['data_dimension']:
            """如果是二维数据，直接转成DataFrame
            """
            y_data = group_data_fine                        
            df = self.to_df(y_data, y_varname, x_data, x_varname)

            return df

        if 3 == group_info['data_dimension']:
            """如果是三维数据，将x-z数据转成DataFrame之后
            用y_varname作为键值存储于字典中
            """            
            x_varname = [group_info['xz_var'][idx] for idx, meth in enumerate(group_info['xz_meth']) if meth ==2]
            z_varname = [group_info['xz_var'][idx] for idx, meth in enumerate(group_info['xz_meth']) if meth ==3][0]
            z_varname_show = [f'{z_varname} = {v}' for v in group_info['z_val']]
            
            data = {varname: self.to_df(group_data_fine[index], z_varname_show, x_data, x_varname) 
                      for index, varname in enumerate(y_varname)}

            return data

    @staticmethod
    def to_df(y_arr, y_varname, x_arr, x_varname):
        """将要显示的横坐标和纵坐标数据整合成DataFrame结构

        注意：这里的横轴坐标不等同于上述x,y轴
        
        Arguments:
            y_arr {np.arrray} -- 纵轴数据
            y_varname {list} -- 纵轴变量名
            x_arr {np.array} -- 横轴数据
            x_varname {list} -- 横轴变量名
        
        Returns:
            pd.DataFrame -- 包含横纵坐标数据和标签的2D结构
        """
        xy_data = np.concatenate((x_arr, y_arr), axis=0)
        xy_varname = x_varname + y_varname
        df = pd.DataFrame(xy_data.T, columns=xy_varname)

        return df


if __name__ == "__main__":
    folder = r"E:\WorkSpace\5_Projects\Control_Space\201912\GW140P3000TG110_Sinoma68.6B_pinggushan_20191224_G0\D1\014ba-3\run"
    sims_data = SimData(folder)
    sims_with_vars = sims_data.all_sims()
    df = sims_data.get_data(sims_with_vars, '0', 'External Controller data 1')    

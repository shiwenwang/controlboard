import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString
import logging
import os
import re
import numpy as np
import pandas as pd


logging.basicConfig(level=logging.DEBUG)
class XML:
    def __init__(self):
        self._tree = None
        self._channels = None
        self._tables = None

    @property
    def tree(self):
        return self._tree    

    @tree.setter
    def tree(self, _tree):
        if isinstance(_tree, ET.ElementTree):
            self._tree = _tree
        else:
            raise ValueError('tree must be a instance of xml.etree.ElementTree.ElementTree')

    @property
    def channels(self):
        return self._channels

    @property
    def tables(self):
        return self._tables

    def verification(self, filename):
        if os.path.isfile(filename) and os.path.splitext(filename)[1] == '.xml':
            return True
        else:
            raise FileNotFoundError("文件不存在或不是'.xml'格式！")

    def open(self, filename):
        if self.verification(filename):     
            self._tree = ET.parse(filename)
            root_child = [child for child in self.tree.getroot()]
            self._channels = root_child[0]
            self._tables = root_child[1]

    def query(self, key_word, name_only=False, strict=False):
        result_list = []

        condition = lambda x, k, s: k.upper() == x.find('Name').text.upper() if s \
                    else k.upper() in x.find('Name').text.upper()

        for ch in self.channels:
            if condition(ch, key_word, strict):
                result_list.append(ch)          
        for tb in self.tables:
            if condition(tb, key_word, strict):
                result_list.append(tb)

        if name_only:
            result = [r.find('Name').text for r in result_list]
        else:
            result = result_list
        return result
        
    def find(self, name):        
        eles = self.query(name, strict=True)
        if eles:
            ele = eles[0]
            name = ele.find('Name').text
            if 'P_' in name:
                value = ele.find('InitialValue').text
                result = {name: value}
            elif 'T_' in name:
                length = int(ele.find('Length').text)
                columns = [f'_{str(n)}' for n in range(length)]
                columns.insert(0, 'Enabled')

                values = []
                rows = ele.findall('Row')
                for i, row in enumerate(rows):                
                    cols = row.findall('Value')
                    col_list = []
                    for j in range(length):
                        col_list.append(cols[j].text)
                    values.append(col_list)
                values = np.insert(np.array(values), 0, [ele.find('Enabled').text, 0], 1)
                
                df = pd.DataFrame(values, columns=columns)
                result = {name: df}
            elif 'F_' in name:
                columns = ["Enabled", "Numerator_Type", "Denominator_Type", "Numerator_TC", 
                        "Denominator_TC", "Numerator_Frequency", "Numerator_Damping_Ratio", 
                        "Denominator_Frequency", "Denominator_Damping_Ratio", "W0", "Prewarping_Wc"
                        ]
                n_rows = int(ele.find('RowCount').text)
                length = 11
                values = []
                rows = ele.findall('Row')
                for i, row in enumerate(rows):                
                    cols = row.findall('Value')
                    col_list = []
                    for j in range(length):
                        col_list.append(cols[j].text)
                    values.append(col_list)
                df = pd.DataFrame(np.array(values), columns=columns)
                result = {name: df}
            else:
                result = {}
        else:
            result = {}

        return result

    def update(self, **kwargs):
        for k, v in kwargs.items():
            if 'P_' in k:
                for ch in self.channels:
                    name = ch.find('Name')
                    if name.text == k:
                        self._update_P(ch, v)
            elif 'T_' in k:
                for tb in self.tables:
                    name = tb.find('Name')
                    if name.text == k:
                        self._update_T(tb, v)
            elif 'F_' in k:
                for tb in self.tables:
                    name = tb.find('Name')
                    if name.text == k:
                        self._update_F(tb, v)
            else:
                pass

    @staticmethod
    def _update_P(ele, value):
        iv = ele.find('InitialValue')
        iv.text = str(value)

    @staticmethod
    def _update_T(ele, value):
        """value is a instance of DataFrame"""
        none_cols = [c for c in value.columns if value.at[0, c] == 'None']
        valide_value = value.drop(none_cols, axis=1)

        enabled = valide_value.at[0, 'Enabled']
        row_count = 2
        length = valide_value.shape[1] - 2

        ele.find('Enabled').text = str(enabled)
        ele.find('RowCount').text = str(row_count)
        ele.find('Length').text = str(length)

        # 删除所有行中的value
        for row in ele.findall('Row'):
            for val in row.findall('Value'):
                row.remove(val)

        # 重新创建
        for i, row in enumerate(ele.findall('Row')):
            for j in range(length):
                new_ele = ET.Element('Value')
                new_ele.attrib = {'Name': f'_{j}'}
                new_ele.text = str(valide_value.at[i, f'_{j}'])
                row.append(new_ele)

    @staticmethod
    def _update_F(ele, value):
        """value is a instance of DataFrame"""
        none_cols = [c for c in value.columns if value.at[0, c] == 'None']
        valide_value = value.drop(none_cols, axis=1)

        row_count = valide_value.shape[0]
        length = 11

        ele.find('RowCount').text = str(row_count)
        ele.find('Length').text = str(length)

        # 删除所有行
        for row in ele.findall('Row'):
            ele.remove(row)

        value_name = ["Enabled", "Numerator_Type", "Denominator_Type", "Numerator_TC", 
                      "Denominator_TC", "Numerator_Frequency", "Numerator_Damping_Ratio", 
                      "Denominator_Frequency", "Denominator_Damping_Ratio", "W0", "Prewarping_Wc"
        ]

        # 重新创建
        for i in range(row_count):
            new_row = ET.Element('Row')
            for name in value_name:
                new_ele = ET.Element('Value')
                new_ele.attrib = {'Name': name.replace('_', '')}
                new_ele.text = str(valide_value.at[i, name])
                new_row.append(new_ele)

            ele.append(new_row)

    def write(self, dst):
        tree_string = ET.tostring(self.tree.getroot()).decode()
        tree_string = re.sub(r'>\s*<', '><', tree_string)
        with parseString(tree_string.encode()) as dom:
            pretty_xml = dom.toprettyxml(indent="  ", newl="\n", encoding='utf-8')

        with open(dst, 'wb') as f:
            f.write(pretty_xml)

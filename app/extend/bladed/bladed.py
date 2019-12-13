import re
import os
from subprocess import Popen, TimeoutExpired, PIPE, STDOUT
from multiprocessing import Process
import logging


class Bladed(object):

    def __init__(self, path):
        self.content = None
        self.path = path
        with open(path, 'r') as f:
            self.content = f.read()

    @property
    def version(self):
        return self.get_version()

    def get_version(self):
        m = re.search(r'VERSION[\t ]+(\d\.\d*)', self.content)
        if m is None:
            result = "unknow"
        else:
            result = m.groups()[0]
        return result

    def query(self, param, number_only=True):
        """
        params = 'RHO'
        result.query(params) => ('RHO', '1.225')
        """
        if self.version == '4.7' and param in ['GTMAX']:
            mapping = {'GTMAX': 'torqueDemandMax'}
            return self.query_v47(mapping[param])

        if number_only:
            pattern = re.compile(
                r'(%s)[\t ]+(-?\d*\.*\d*E?-?\+?\d*)\n' % param)
        else:
            pattern = re.compile(r'(%s)[\t ]+(.*)\n' % param)
        result = pattern.search(self.content)

        if result is None:
            return None

        data = (float(result.group(2)) if '.' in result.group(2) else int(result.group(2))) \
            if number_only else result.group(2)

        return result.group(1), str(data)

    def query_v47(self, param):
        result = re.search(r'<(%s)>(\d*)<' % (param, ), self.content)

        return (param, '') if result is None else result.groups()

    def set(self, number_only=True, write=True, **kwargs):
        for key, value in kwargs.items():
            if number_only:
                pattern = re.compile(
                    r'((%s)[\t ]+)-?\d*\.*\d*E?-?\+?\d*\n' % key)
            else:
                pattern = re.compile(r'((%s)[\t ]+)(.*)\n' % key)
            self.content = pattern.sub(
                lambda m: m.groups()[0] + str(value) + '\n', self.content, 1)

        if write:
            with open(self.path, 'w') as f:
                f.write(self.content)

    def modify_v47(self):        
        self.content = self.content.replace('<AerodynamicModule>New<', '<AerodynamicModule>Old<')
        self.set(NBLADE=11, BDAMP='.005 .005 .005 .005 .005 .005 .005 .005 .005 .005 .005', write=False)
        self.content = self.content.replace('0RMODE\n', '')
        self.content = re.sub(r'DTBLADEDi.*DTBLADEDa\t""', '', self.content, flags=re.S)
        self.content = re.sub(r'MSTART RMODE.*?MEND', '', self.content, flags=re.S)        

        with open(self.path, 'w') as f:
            f.write(self.content)

    def solo_run(self, run_dir, dll_path, xml_path, name=None, windf=None):
        name = os.path.splitext(os.path.basename(self.path))[0] if name is None else name
        if '0RMODE' not in self.content:
            modal_dir = os.path.abspath(os.path.join(run_dir, 'modal'))
            success = self.modal_analysis(modal_dir)
            if not success:
                os._exit(0)  # modal 计算失败，及时退出子进程
        self.content = re.sub(r'<Filepath>.*</Filepath>', lambda m: f'<Filepath>{dll_path}</Filepath>', self.content)
        self.content = re.sub(r'<AdditionalParameters>.*</AdditionalParameters>', lambda m:
                              f'<AdditionalParameters>READ {xml_path}</AdditionalParameters>', self.content)

        with open(self.path, 'w') as f:
            f.write(self.content)
        if windf is not None:
            self.set(windf=windf, number_only=False)
        proc = Process(target=self.run, args=(run_dir, name))
        proc.start()
        proc.join()

    def campbell(self, run_dir):        
        if self.version == '4.7':
            self.modify_v47()

        if '0RMODE' not in self.content:
            modal_dir = os.path.abspath(os.path.join(run_dir, 'modal'))
            success = self.modal_analysis(modal_dir)
            if not success:
                os._exit(0)  # modal 计算失败，及时退出子进程

        cut_in = self.query('CUTIN')[1]
        cut_out = self.query('CUTOUT')[1].split('.')[0]  # 等同向下取整
        if '0LINEARISE' not in self.content:
            linearise_block = '\n'.join([
                                'MSTART LINEARISE',
                                'LINIDLING	0',
                                'LINPOWPROD	-1',
                                'LINTYPE	 1',
                                'WRLO	 0',
                                'WRHI	 0',
                                'WRSTEP	 .1047197',
                                'IDLEWIND	 10',
                                f'WINDLO	 {cut_in}',
                                f'WINDHI	 {cut_out}',
                                'WINDSTEP	 1',
                                'AZLO	 0',
                                'AZHI	 0',
                                'AZSTEP	 1.745328E-02',
                                'WINDPERT	 0',
                                'INDIVWIND	 0',
                                'PITCHPERT	 0',
                                'INDIVPITCH	 0',
                                'QGPERT	 0',
                                'MAXFREQ	 1',
                                'CCCRIT	 .8',
                                'MBCFLAG	 0',
                                'MEND\n',
                                'MSTART ADAT'
                                ])
            self.content = self.content.replace('MSTART ADAT', linearise_block)
            self.content = self.content.replace('0LOSS', '0LINEARISE\n0LOSS')
        else:
            key_value = {"LINIDLING": "0", "LINPOWPROD": "-1", "LINTYPE": 1,
                         "WINDLO": cut_in, "WINDHI": cut_out}
            self.set(**key_value)

        self.set(CALCULATION='33', OPTIONS='212754')
        # self.run(run_dir)
        proc = Process(target=self.run, args=(run_dir, 'lin1'))
        proc.start()
        proc.join()

    def modal_analysis(self, run_dir):
        self.set(CALCULATION="2", OPTIONS="0")
        proc = Process(target=self.run, args=(run_dir, ))
        proc.start()
        proc.join()
        # self.run(run_dir)
        out_path = os.path.abspath(os.path.join(run_dir, 'DTEIGEN.OUT'))
        try:
            with open(out_path, 'r') as f:
                out = f.read()
        except FileNotFoundError:
            logging.warning(f'FileNotFoundError: {out_path}')
            return False
        m_rmode = re.search(r'MSTART RMODE.*MEND', out, re.DOTALL)
        if m_rmode is None:
            return False
        rmode = m_rmode.group()
        self.content = self.content.replace(
            '\n\t\t]]>', '\n0RMODE\n' + rmode + '\n\n\t\t]]>')

        m_ipw = re.search(r'IPW[\t ]+(\S+)\n', out)
        m_lpw1 = re.search(r'LPW1[\t ]+(\S+)\n', out)
        m_ipw1 = re.search(r'IPW1[\t ]+(.+)MSTART RMODE', out, re.DOTALL)
        if m_ipw is None or m_ipw1 is None:
            return False
        ipw, lpw1 = m_ipw.group(1), m_lpw1.group(1)
        ipw1 = re.sub(r',\s*', ', ', m_ipw1.group(1)).strip()  # 调整到一行显示

        self.set(number_only=False, IPW=ipw, IPW1=ipw1, LPW1=lpw1)
        return True

    def run(self, run_dir, run_name=None, **env):
        """
        [执行Bladed中的 "RUN NOW" ] 

        该函数应该在子进程中运行，避免web主进程阻塞！！！

        Arguments:
            run_dir {[str]} -- [计算结果所在文件夹]
            env {[dict]} -- [命令行执行所需的环境变量，例如：计算所需的mclmcrrt72.dll的路径需指定到PATH中(dtlinmod)]
        """
        bladed_dir_map = {
            'BLADED_V3.82': 'C:\\Program Files (x86)\\GH Bladed 3.82',
            'BLADED_V4.3': 'C:\\Program Files (x86)\\Bladed 4.3',
            'BLADED_V4.6': 'C:\\Program Files (x86)\\DNV GL\\Bladed 4.6',
            'BLADED_V4.7': 'C:\\Program Files (x86)\\DNV GL\\Bladed 4.7',
        }

        bladed_dir = os.environ.get(f'BLADED_V{self.version}') or bladed_dir_map[f'BLADED_V{self.version}']

        bladed_m72_path = os.path.abspath(
            os.path.join(bladed_dir, 'Bladed_m72.exe'))        

        # 生.in文件        
        if run_name is None:
            proc_batch = Popen(
            [bladed_m72_path, '-Prj', self.path, '-RunDir', run_dir],
            stdout=PIPE, stderr=STDOUT)
        else:
            run_path = os.path.abspath(os.path.join(run_dir, run_name))
            proc_batch = Popen(
                [bladed_m72_path, '-Prj', self.path, '-RunDir', run_dir, '-ResultsPath', run_path],
                stdout=PIPE, stderr=STDOUT)
        try:
            proc_batch.communicate(timeout=60)
        except TimeoutExpired:
            proc_batch.kill()
            os._exit(0)  # 退出当前进程

        # 计算
        bladed_dtbladed_path = os.path.abspath(
            os.path.join(bladed_dir, 'DTBLADED.exe'))
        batch_dtbladed_path = os.path.join(run_dir, 'DTBLADED.IN')

        proc_dtbladed = Popen(
            [bladed_dtbladed_path, batch_dtbladed_path], cwd=run_dir,
            stdout=PIPE, stderr=STDOUT)

        proc_dtbladed.communicate()


if __name__ == "__main__":
    import os
    here = os.path.abspath(os.path.dirname(__file__))
    v38 = os.path.join(here, '../../../data/bladed/v382.$PJ')
    v43 = os.path.join(here, '../../../data/bladed/v43.$PJ')
    v46 = os.path.join(here, '../../../data/bladed/v46.$PJ')

    bladed_v38 = Bladed(v38)
    bladed_v43 = Bladed(v43)
    bladed_v46 = Bladed(v46)

    print(bladed_v38.version())
    print(bladed_v43.version())
    print(bladed_v46.version())

    print(bladed_v43.query("RHO"))
    print(bladed_v43.query("PITMIN"))
    print(bladed_v43.query("OMMAX"))

    bladed_v43.set(RHO=1.225, OMMIN=0.10101, OMMAX=9.9999)

    print(bladed_v43.query("RHO"))
    print(bladed_v43.query("OMMIN"))
    print(bladed_v43.query("OMMAX"))

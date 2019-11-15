import re


class Bladed(object):

    def __init__(self, path):
        self.content = None
        self.path = path
        with open(path, 'r') as f:
            self.content = f.read()

    def version(self):
        pattern = re.compile(r'VERSION\s+(\d\.\d*)')

        m = pattern.search(self.content)
        if m is None:
            result = "unknow"
        else:
            result = m.groups()[0]
        return result

    def query(self, param):
        """
        params = 'RHO'
        result.query(params) => ('RHO', '1.225')
        """
        if self.version() == '4.7' and param in ['GTMAX']:
            mapping = {'GTMAX': 'torqueDemandMax'}
            return self.query_v47(mapping[param])

        pattern = re.compile(r'(%s)\s+(-?\d*\.*\d*E?-?\+?\d*)\n' % param)
        result = pattern.search(self.content)

        return (param, '') if result is None else (result.groups()[0], str(float(result.groups()[1])))

    def query_v47(self, param):
        pattern = re.compile(r'<(%s)>(\d*)<' % (param, ))
        result = pattern.search(self.content)

        return (param, '') if result is None else result.groups()

    def set(self, **kwargs):
        for key, value in kwargs.items():
            pattern = re.compile(r'((%s)\s+)-?\d*\.*\d*E?-?\+?\d*\n' % key)
            self.content = pattern.sub(
                lambda m: m.groups()[0] + str(value) + '\n', self.content, 1)

        with open(self.path, 'w') as f:
            f.write(self.content)


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

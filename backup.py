# coding:utf-8
"""
This script handles backup tasks. The configuration is in ./res/device.yaml. The session is ssh preferred.
running ok in python 3.5.

author: Yunfan

Date: 20170111

usage:
    >>> A = task()
    >>> A.execute_pool()
"""

import time
import datetime
import os
import codecs
import re
import IPy
from multiprocessing.dummy import Pool as ThreadPool
from logger import logger


class Task(object):
    def __init__(self):
        self._max_pools = 200
        self._pool_number = 10
        self.filename = ''
        # conf is a dict, key of which is ip with its content the configuration. The configuration of an ip is a dict.
        self.conf = {}
        self.hosts = [] # key of conf, bad design

    def empty(self):
        self._pool_number = 10
        self.filename = ''
        self.conf = {}
        self.hosts = []

    def setconf(self, **param):
        _LEASTPARAM = ['METHOD', 'IP', 'EXPORTDIR', 'USERNAME', 'PASSWORD', 'ICMP', 'INTERVALS', 'COMMANDS']
        for key in _LEASTPARAM:
            if key not in param:
                logger.error('PARAMETERS dismatch in task.')
                return None
        # wrong: self.conf = {'Method': param['METHOD'], 'Exportdir': param['EXPORTDIR'], 'Username': param['USERNAME'], 'Password': param['PASSWORD']}
        self.hosts = []

        # IP
        self.conf={}
        self.hosts=[]
        if type(param['IP']) is list:
            for item in param['IP']:
                if type(item).__name__=='unicode' or type(item) is str:
                    self.conf[item] = {'IP': item}
                    self.hosts.append(item)
                elif type(item) is dict:
                    for key in item:
                        self.conf[item[key]] = {'IP': item[key], 'Name': key}
                        self.hosts.append(item[key])
        elif type(param['IP']).__name__=='unicode' or type(param['IP']) is str:
            raw = param['IP']
            splitter = ''
            for i in [',', ';','/r/n','/r','n']:
                if i in raw:
                    splitter=i
                    break
            if splitter == '':
                self.conf[raw] = {'IP': raw}
                self.hosts.append(raw)
            else:
                for item in raw.strip(' ').split(splitter):
                    self.conf[item] = {'IP': item}
                    self.hosts.append(item)

        # implement necessary info
        for key in self.conf:
            self.conf[key].update({'Method': param['METHOD'], 'Exportdir': param['EXPORTDIR'], 'Username': param['USERNAME'],
                     'Password': param['PASSWORD']})

        # COMMANDS: should be converted to a list
        for key in self.conf:
            self.conf[key]['Commands'] = []
            if ',' in param['COMMANDS']:
                self.conf[key]['Commands'] = param['COMMANDS'].split(',')
            elif ';' in param['COMMANDS']:
                self.conf[key]['Commands'] = param['COMMANDS'].split(';')
            elif '/r/n' in param['COMMANDS']:
                self.conf[key]['Commands'] = param['COMMANDS'].split('/r/n')
            elif '/r' in param['COMMANDS']:
                self.conf[key]['Commands'] = param['COMMANDS'].split('/r')
            elif '/n' in param['COMMANDS']:
                self.conf[key]['Commands'] = param['COMMANDS'].split('/n')
            else:
                self.conf[key]['Commands'] = [param['COMMANDS']]

        # INTERVALS
        for key in self.conf:
            self.conf[key]['Interval'] = []
            try:
                if u'INTERVALS' in param:
                    t = param['INTERVALS']
                    if (type(t) is int) or (type(t) is float):
                        self.conf[key]['Interval'] = [float(t)] * len(self.conf[key]['Commands'])
                    elif type(t).__name__=='unicode' or type(t) is str:
                        t = t.strip(' ')
                        if ',' in t:
                            t = t.split(',')
                        elif ';' in t:
                            t = t.split(';')
                        else:
                            t=[float(t)] * len(self.conf[key]['Commands'])
                        for i in t:
                            self.conf[key]['Interval'].append(float(i))
                        if len(self.conf[key]['Interval']) < len(self.conf[key]['Commands']):
                            self.conf[key]['Interval'] += [0.2] * (len(self.conf[key]['Commands'])-len(self.conf[key]['Interval']))
                else:
                    self.conf[key]['Interval'] = [0.2] * len(self.conf[key]['Commands'])
            except ValueError:
                self.conf[key]['Interval'] = [0.2] * len(self.conf[key]['Commands'])

        # ENFORCE
        for key in self.conf:
            self.conf[key]['Enforce'] = True
            if 'ENFORCE' in param:
                if param['ENFORCE'] in [0, '0', '0.0', False, 'False', 'false', 'FALSE', 'no', 'NO', 'No']:
                    self.conf[key]['Enforce'] = False
        # ICMP
        for key in self.conf:
            self.conf[key]['ICMP'] = False
            if 'ICMP' in param:
                if param['ICMP'] in [1, '1', '1.0', True, 'True', 'true', 'TRUE', 'yes', 'YES', 'Yes']:
                    self.conf[key]['ICMP'] = True
        # Manufacturer
        for key in self.conf:
            self.conf[key]['Manufacturer'] = '' if u'MANUFACTURER' not in param else param[u'MANUFACTURER']

    def read_conf(self, filename='../res/device.yaml'):
        """
        This function read the configuration from yaml and json. 读取文件时对ip地址检查。
        :param filename:
        :return:
        """
        logger.debug('Read configuration: %s' % filename)

        self.conf = {}
        self.hosts = []
        self.filename = filename
        if '.yaml' in filename:
            try:
                import yaml
                conf = (yaml.load(open(filename, 'r')))  # read a single YAML document.
                if 'operations' in conf:
                    'Operation Starts!'
                    operations = conf['operations']
                    for key in operations.keys():
                        if key == 'ThreadPool':
                            if type(operations['ThreadPool']) is int:
                                self._pool_number = operations['ThreadPool']
                        elif conf['operations'][key]['Method'].lower() == 'ssh':
                            ssh = conf['operations'][key]
                            # ip 地址可以是列表[]或者字典{'文件名':ip,}
                            if isinstance(ssh['IP'], list):
                                for ip in ssh['IP']:
                                    item = {}
                                    item['IP'] = IPy.IP(ip).__str__()
                                    item['Name'] = item['IP']
                                    item['Method'] = 'ssh'
                                    for attribute in ssh:
                                        if attribute == 'IP':
                                            continue
                                        item[attribute] = ssh[attribute]
                                    self.conf[ip] = item
                                    self.hosts.append(ip)

                            elif isinstance(ssh['IP'], dict):
                                for ip in ssh['IP']:
                                    item = {}
                                    # check whether the ip is valid
                                    item['IP'] = IPy.IP(ssh['IP'][ip]).__str__()
                                    item['Method'] = 'ssh'
                                    item['Name'] = ip
                                    for attribute in ssh:
                                        if attribute == 'IP':
                                            continue
                                        item[attribute] = ssh[attribute]
                                    self.conf[item['IP']] = item
                                    self.hosts.append(item['IP'])

            except Exception as e:
                logger.error(e.__str__())
            finally:
                pass

        elif '.json' in filename:
            import json
            fp = open(filename, 'r')
            self.conf = json.load(fp)
            fp.close()
            self.hosts = []
            for host in self.conf:
                self.hosts.append(host)

    def save_conf(self, filename='device.json'):
        import json
        fp = open(filename, 'w')
        json.dump(self.conf, fp)
        fp.close()
        logger.info('Read configuration successfully.')

    def execute_pool(self, filename='../res/device.yaml'):
        """
        Multi-thread tasks.
        """
        try:
            if type(filename) is str:
                self.read_conf(filename)
        except Exception as e:
            logger.error('Failed to read configuration file.')
            return
        # for debug
        # self.save_conf()
        if (self._pool_number > self._max_pools): self._pool_number = self._max_pools
        pool = ThreadPool(self._pool_number)
        results = pool.map(self.execute, self.hosts)
        pool.close()
        pool.join()
        return results

    def execute(self, parameter):
        if self.conf[parameter]['Method'] == 'ssh':
            # modified the output directory if time style expression found in the config
            now = datetime.datetime.now()
            export_path = os.getcwd() + os.path.sep + self.conf[parameter]['Exportdir']
            try:
                otherStyleTime = os.path.split(export_path)[1]
                otherStyleTime = now.strftime(os.path.split(export_path)[1])
            finally:
                export_path = os.path.split(export_path)[0] + os.path.sep + otherStyleTime
            if not os.path.isdir(export_path):
                os.mkdir(export_path)
            # do the ssh operation
            return(self.ssh(ip=self.conf[parameter]['IP'], username=self.conf[parameter]['Username'],
                     password=self.conf[parameter]['Password'], manufacturer=self.conf[parameter]['Manufacturer'],
                     cmds=self.conf[parameter]['Commands'], interval=self.conf[parameter]['Interval'],
                     exportdir=export_path, enforce=self.conf[parameter]['Enforce'], icmp=self.conf[parameter]['ICMP'],
                     filename=self.conf[parameter]['Name']))

    def ssh(self, ip, port=22, username='', password='', manufacturer='', cmds=[], interval=[], exportdir='',
            enforce=True, errcode=['Error', 'error'], icmp=True, filename=''):
        output = ''
        status = ''
        try:
            import paramiko
            logger.info(u'Trying to connect %s', ip)
            if not (icmp & self.ping(ip).__eq__('NA')):

                # logger.info('username: %s, password: %s', username, password)
                remote_conn_pre = paramiko.SSHClient()
                remote_conn_pre.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                remote_conn_pre.connect(ip, port=port, username=username,
                                        password=password,
                                        look_for_keys=False,
                                        allow_agent=False
                                        )
                remote_conn = remote_conn_pre.invoke_shell()
                output += remote_conn.recv(65535)
                ind = 0
                if type(cmds) != list:
                    cmds = list(cmds)

                while (ind < cmds.__len__()):
                    val = cmds[ind]
                    data = str(val + '\n')
                    remote_conn.send(data)
                    if ((interval == []) | ind >= interval.__len__() | (interval[ind] == 0)):
                        sleeptime = 0.2
                    else:
                        sleeptime = float(interval[ind])
                    time.sleep(sleeptime)
                    outputline = str(remote_conn.recv(65535))
                    # 遇到more，自动输入空格，增加延时0.2秒
                    if outputline.find('More') >= 0:
                        if ind + 1 == cmds.__len__():
                            cmds.append(' ')
                            interval.append(0.2)
                        else:
                            cmds.insert(ind + 1, ' ')
                            interval.insert(ind + 1, 0.2)
                    ind += 1
                    outputline = self.prettyoutput(outputline,
                                                   [chr(27), u' --More-- ', u'        ',
                                                    u'  ---- More ----', u'[16D                [16D'], '')
                    output += outputline
                    if (self.haserr(output, errcode) | enforce.__eq__('False') | enforce == 0):
                        logger.error('Error found, stop@%s, %s', val, output)
                        break
                # logger.info(cmds)
                remote_conn.close()
                remote_conn_pre.close()
            else:
                status = 'The host is unreachable.'
        # except Exception:
        #    logger.info(Exception.)
        finally:
            if (status.__eq__('The host is unreachable.')):
                logger.info('The host %s is unreachable.' % ip)
                return {ip: 'unreachable'}
            if (output.__eq__('')):
                logger.info(ip + ': Nothing Received')
                return {ip: ''}
            elif exportdir.__eq__(''):
                logger.info('exportdir is empty. Return result string.')
                return {ip: output}
            else:
                if filename.__eq__(''): filename = str(ip)
                exportdir = exportdir + os.path.sep + filename + '.txt'
                f = codecs.open(exportdir, 'w', 'utf-8')
                for line in output:
                    f.write(line)
                f.close()
                logger.info(filename + ' configuration saved successfully!')
                return {ip: 'ok'}

    @classmethod
    def prettyoutput(self, message, oldReplace, newRlace):
        result = message
        # tmp1 = re.search(r'(?P<dust>.)\[16D',message)
        # if tmp1:
        #    result = result.replace(tmp1.group('dust'),'')
        #    print chr(27)
        for i in oldReplace:
            result = result.replace(i, newRlace)
        return result

    @classmethod
    def ping(self, IP=str):
        """
        pexpect supported icmp utility.
        :param IP:
        :return: Access or NA
        """
        # test = pexpect.spawn("ping -c3 -t1 %s" % (IP))
        # result = "Access"
        # try:
        #     result = "NA" if test.expect([pexpect.TIMEOUT, "3 packets transmitted, 0 received.*"], 3) != 0 else "Access"
        # finally:
        #     return result

        result = 'Access'
        try:
            from subprocess import Popen, PIPE
            import platform
            result = 'NA'
            process = Popen("ping -c 3 -w 3 " + IP, stdout=PIPE, shell=True)
            test, unused_err = process.communicate()
            tmp1 = re.search(r'rtt min/avg/max/mdev = ([0-9\.]+)/([0-9\.]+)/([0-9\.]+)/([0-9\.]+)', test)
            if tmp1:
                result = 'Access'
        finally:
            return result

    @classmethod
    def haserr(self, raw, err):
        for i in err:
            if raw.__contains__(i):
                return True
        return False


if __name__ == "__main__":
    # instance
    A = task()
    # input the configuration file name
    # A.execute_pool('../res/device.yaml')
    A.read_conf()
    A.save_conf()

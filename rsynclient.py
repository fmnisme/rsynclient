#coding:utf-8
"""
封装rsync客户端命令
"""
import sys
import os
import getopt
import itertools
import subprocess
import thread
import Queue
import platform

if platform.system()=='Windows':
    _bin_path=r'E:\"Program Files (x86)"\cwRsync_5.3.0_Free\rsync.exe'
else:
    _bin_path='rsync'
_default_user='rsyncuser'
_default_arg='-vzrt  --delete'
_thread_num=10
_help_d={'-s':'(必选) 本地目录/文件。例如 E:\\tmp',
         '-h':'(必选) 目的ip。支持“, -”批量操作符，列如192.168.1,3-5.100',
         '-m':'(必选) 模块名',
         '-u':'用户名。默认：%s'%(_default_user),
         '-p':'密码文件路径。列如 E:\\passwd\\userpasswd.txt'}
_help='\r\n'.join(['%s %s'%(k,v) for (k,v) in _help_d.iteritems()])
_help='全部参数:\r\n'+_help
_help+='''\r\n\r\n样列:
windows:
    rsynclient.py -h 192.168.1.2 -s E:\da\da -m xxxx
linux:
    python26 rsynclient.py  -h 192.168.1.2 -s /data/xx -m xxxx'''
_help+='\r\n\r\n有问题请联系：徐鸿鹄'


def check_num(func):
    """装饰器
    检查传入的数字参数格式是否有问题。
    """
    def t(arg):
        #right=[str(n) for n in range(10)]+[',','-']

        arg=arg.replace(' ','') #去掉空格

        #res=[x for x in arg if x not in right]
        #if res:
        #    raise NUMARG_ERROR('args err!1')

        res=[x for x in [',','-'] if arg.startswith(x) or arg.endswith(x)]
        if res:
            raise NUMARG_ERROR('ip格式错误！')

        err_arg=[',-','-,','--',',,']
        res=[x for x in err_arg if x in arg]
        if res:
            raise NUMARG_ERROR('ip格式错误！')
        return func(arg)
    return t

class NUMARG_ERROR(Exception):
    def __init__(self,value):
        self.value=value

    def __str__(self):
        return self.value+'\r\n\r\n'+_help

class ARG_ERROR(Exception):
    def __init__(self,value):
        self.value=value
    def __str__(self):
        return self.value+'\r\n\r\n'+_help

def catch_exception(func):
    """装饰器
    捕获异常"""
    def t(*args,**kwargs):
        try:
            return func(*args,**kwargs)
        except NUMARG_ERROR,e:
            return e.__str__()
        except ARG_ERROR,e:
            return  e.__str__()
        except getopt.GetoptError,e:
            return '-%s %s\r\n\r\n%s'%(e[1],_help_d['-'+e[1]],_help)
        except:#打印所有未知异常
            import cStringIO
            import traceback
            err_fp = cStringIO.StringIO() #创建内存文件对象
            traceback.print_exc(file=err_fp)
            err_msg = err_fp.getvalue()
            err_msg='\r\n'.join(err_msg.split( '\n'))
            #self.response.out.write(err_msg)
            return  err_msg
    return t

@check_num
def extend_num(arg):
    """将- ,扩展成数字列表"""
    res=[]
    if ',' in arg:
        s=arg.split(',')
        for x in s:
            if '-' in x:
                #e.g.：将21-25，切割成21和25，并转换成数字，然后用range 循环获取端口，最后将端口转换成字符串返回
                y=[ str(xx).decode('utf-8') for xx in range(int(x.split('-')[0].strip()),int(x.split('-')[1].strip())+1)]
                res.extend(y)
            else:
                res.append(x.strip())
    elif '-' in arg:#这里说明只有一个区间,如果有多个区间的话，使用逗号隔开，就会满足上个if条件
        x=arg   #与上面的列表推导参数保持一致
        y=[ str(xx).decode('utf-8') for xx in range(int(x.split('-')[0].strip()),int(x.split('-')[1].strip())+1)]
        res.extend(y)
    else:
        res.append(arg.strip())
    res=dict.fromkeys(res).keys()    #过滤掉重复的值
    res.sort()
    return res

def to_rsync_path(path):
    """转换成rsync模式的路径"""
    if platform.system()=='Windows':
        rsync__path=os.path.abspath(path)
        rsync__path=rsync__path.replace('\\','/')
        rsync__path=rsync__path.replace(':','')
        rsync__path='/cygdrive/'+rsync__path
        if path.endswith('\\'):
            rsync__path+='/'
        return rsync__path
    else:
        return path

@catch_exception
def run(*argv):
    """主方法，执行命令
    xxx.py -h ip地址 -m 模块 -s 同步文件或目录
    rsync -vzrt --progress --delete /cygdrive/e/tmp/tmp[1-2]  user1@58.22.103.208::rsync_1"""
    opts,args=getopt.getopt(argv,'h:m:s:u:p:')
    kwargs=dict(opts)

    #检查参数是否足够
    if not kwargs.has_key('-h') or  not kwargs.has_key('-s') or  not kwargs.has_key('-m'):
        raise ARG_ERROR('参数不足!')
        print '--help'
    if kwargs.has_key('-u') and not kwargs.has_key('-p'):
        raise ARG_ERROR('密码参数-p没有指定!')

    #使用默认用户认证
    if kwargs.has_key('-p') and not kwargs.has_key('-u'):
        kwargs['-u']=_default_user

    #将路径转换为rsync能识别的格式
    kwargs['-s']=to_rsync_path(kwargs['-s'])
    if kwargs.has_key('-p'):
        kwargs['-p']=to_rsync_path(kwargs['-p'])

    #扩展ip
    ips=[]
    try:
        ip_seq1,ip_seq2,ip_seq3,ip_seq4=kwargs['-h'].split('.')
        for num1,num2,num3,num4 in itertools.product(extend_num(ip_seq1),extend_num(ip_seq2),extend_num(ip_seq3),extend_num(ip_seq4)):
            ips.append('%s.%s.%s.%s'%(num1,num2,num3,num4))
    except:
        raise NUMARG_ERROR('ip格式错误!')

    #启动线程
    queue=Queue.Queue()
    for x in range(_thread_num):
        thread.start_new_thread(_work_thread,(queue,))

    for ip in ips:
        if kwargs.has_key('-u'):
            cmd='%s %s "%s" %s@%s::%s --password-file=%s'%(_bin_path,_default_arg,kwargs['-s'],kwargs['-u'],ip,kwargs['-m'],kwargs['-p'])
        else:
            cmd='%s %s "%s" %s::%s'%(_bin_path,_default_arg,kwargs['-s'],ip,kwargs['-m'])
        queue.put([ip,cmd])
    queue.join()

def _work_thread(queue):
    """工作线程，执行命令"""
    while True:
        ip,cmd=queue.get()
        output=subprocess.Popen(cmd.encode('cp936'),shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.read()
        output= '**********%s**********\r\n%s\r\n%s'%(ip,cmd,output)
        if platform.system()=='Windows':
            output=output.decode('utf-8').encode('cp936')
        print output
        queue.task_done()

if __name__=='__main__':
    #run('-h','192.168,169.1.1,2,3','-m')
    argv=sys.argv[1:]
    if argv:
        res=run(*argv)
        if res:
            if platform.system()=='Windows':
                res=res.decode('utf-8').encode('cp936')
            print res
    else:
        if platform.system()=='Windows':
            _help=_help.decode('utf-8').encode('cp936')
        print _help


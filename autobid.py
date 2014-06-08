#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import requests
from lxml import etree
from pyquery import PyQuery
import yaml
import os
import webbrowser
from readbot import ReadBot
import json
import Tkinter as tk
from PIL import Image, ImageTk
import codecs

_debug = False



_rrd_url = 'http://www.renrendai.com'
_rrd_url_loadpage = os.path.join(_rrd_url, 'lend', 'detailPage.action') + '?loanId=%s'

def safe_mkdir(dir):
    if not os.path.isdir(dir):
        os.makedirs(dir)

def check_bid_worth(data):
    if float(data['interest']) >= 15 and int(data['progress']) < 100 and int(data['months']) < 18:
        return True
    else:
        return False

def calc_bid_value(data):
    if float(data['interest']) >= 18 and int(data['months']) <= 18:
        return 100
    else:
        return 50

def toggle_open_browser(loadid):
    url = _rrd_url_loadpage % (loadid)
    webbrowser.open(url)

def ocr_rec(imgfile):
    #rb = ReadBot()
    ##rb.ocr_config = ['digits']
    #rb.ocr_config = ['alnums']
    #result = rb.interpret(imgfile)
    #return result

    # 手动输入验证码
    obj = Captcha(imgfile)
    obj.dialog()
    return obj.value

def logprint(data, info_head='info'):
    if info_head:
        head_str = '[%s] ' % (info_head.upper())
    else:
        head_str = ''
    logstr = '%s%s' % (head_str, data)
    if not _debug and info_head.lower() == 'debug':
        return
    print logstr

class Captcha():
    def __init__(self, imgpath):
        self.imgpath = imgpath
        self.value = ''

    def get_value(self, event):
        self.value = event.widget.get()
        event.widget.master.quit()
        event.widget.master.destroy()

    def dialog(self):
        win = tk.Tk()
        win.geometry('300x300+300+200')

        im = Image.open(self.imgpath)
        tkimage = ImageTk.PhotoImage(im)
        label = tk.Label(win, image=tkimage)
        label.pack() # pady=10)
        entry = tk.Entry(win, text='输入')
        entry.pack()
        entry.focus()
        entry.bind('<Key-Return>', self.get_value)

        win.wm_attributes("-topmost", 1)
        win.focus_force()
        win.mainloop()


BASE_URL = 'http://www.renrendai.com'
class AutoBid(object):
    _keys = ('title', 'company', 'user', 'category', 'money', 'interest', 'months', 'progress')
    cookies = None
    urls = {
        'index': BASE_URL,
        'login': os.path.join(BASE_URL, 'j_spring_security_check'),
        'list': os.path.join(BASE_URL, 'lend', 'loanList!json.action'),
        'post': os.path.join(BASE_URL, 'lend', 'loanLender.action'),
        'codeimg': os.path.join(BASE_URL, 'image.jsp'),
        'account': os.path.join(BASE_URL, 'account', 'index.action'),
        #'detail': os.path.join(BASE_URL, 'lend', 'detailPage.action') + '?loanId=%s',
    }
    success_string = u'恭喜您，投标成功！'

    def __init__(self, config_file=None):
        logprint('AutoBid init...', 'debug')
        if config_file is None:
            config_file = os.path.join(os.path.dirname(__file__),'config.yaml')
        if not os.path.isfile(config_file):
            exit('配置文件不存在(%s)' % (config_file))
        conf = yaml.load(open(config_file))
        logprint(conf, 'debug')
        self.ua = conf['ua']
        self.header = {'user-agent': conf['ua']}
        self.username = conf['username']
        self.password = conf['password']
        self.headers = {'user-agent': conf['ua']}
        # 初始化目录空间
        _base_dir = '/tmp/rrd'
        safe_mkdir(_base_dir)
        self._code_img = os.path.join(_base_dir, 'code.jpeg')
        self._code_img_back_dir = os.path.join(_base_dir, 'img')
        safe_mkdir(self._code_img_back_dir)
        self._err_html_dir = os.path.join(_base_dir, 'errhtml')
        safe_mkdir(self._err_html_dir)

        self.bidlist_file = os.path.join(_base_dir, 'bidlist')
        self.log_file = os.path.join(_base_dir, 'rrd.log')

        self.init_cookies()
        self.login()

    def execute(self):
        if self.money_available() < 50:
            logprint('account money rest: %s' % (self.money_avail))
            return
        logprint('account money rest: %s continue' % (self.money_avail))
        self.find_bid()

    def httpreq(self, method, urlkey, *args, **kwargs):
        logprint('http request: %s' % (urlkey), 'debug')
        if getattr(self, 'r', None) is None:
            self.r = requests.Session()
        if urlkey not in self.urls:
            raise Exception('key(%s) not in urls' % (urlkey))
        url = self.urls[urlkey]
        kwargs['headers'] = self.headers
        #logprint(kwargs, 'debug')
        resp = self.r.request(method, url, *args, **kwargs)
        if resp.status_code >=400:
            raise Exception('http can not response normally(%s)' % (resp.status_code))
        #logprint(resp.cookies, 'debug')
        return resp

    def init_cookies(self):
        resp = self.httpreq('get', 'index')

    @property
    def bidlist(self):
        if os.path.isfile(self.bidlist_file):
            try:
                bidlist = yaml.load(open(self.bidlist_file).read())
            except:
                bidlist = []
        else:
            bidlist = []
        return bidlist

    @bidlist.setter
    def bidlist(self, val):
        bidlist = self.bidlist
        bidlist.append(val)
        yaml.dump(bidlist, open(self.bidlist_file, 'w'))

    def money_available(self):
        resp = self.httpreq('get', 'account')
        pq = PyQuery(resp.text)
        item = pq('span').filter(lambda i: PyQuery(this).text() == u'可用金额')
        if item:
            p = item.nextAll()
            money_avail = p('em').text()
            try:
                money_avail = float(money_avail)
            except:
                money_avail = 0
        else:
            money_avail = 0
        self.money_avail = money_avail
        return money_avail

    def bid_info_format(self, data):
        d = {
            'id': data['loanId'],
            'title': data['title'],
            'company': '',
            'user': data['nickName'],
            'category': '',
            'money': data['amount'],
            'interest': data['interest'],
            'months': data['months'],
            'progress': data['finishedRatio'],
        }
        return d

    def find_bid(self):
        # 请求贷款列表
        resp = self.httpreq('get', 'list')
        # 提取贷款信息
        try:
            datas = json.loads(resp.text).get('data').get('loans', [])
        except:
            datas = []
        for data in datas:
            d = self.bid_info_format(data)
            logprint('%(id)s %(months)2s %(interest)5s %(progress)7s %(title)s %(money)s' % d, 'debug')
            if int(d['progress']) != 100:
                logprint('%(id)s %(months)2s %(interest)5s %(progress)7s %(title)s %(money)s' % d, 'info')
            # progress 字段值不是数字的处理(等待材料的情况)
            if not isinstance(d['progress'], float) and not d['progress'].isdigit():
                continue
            if check_bid_worth(d):
                # already bided check

                print self.bidlist
                if d['id'] not in self.bidlist:
                    # auto bid
                    ret = self.post_bid(d)
                    if ret:
                        self.bidlist = d['id']

                    ### open brower for bid
                    ##self.bidlist = d['id']
                    ##toggle_open_browser(d['id'])

    def login(self):
        login_body = {
            'j_username': self.username,
            'j_password': self.password,
            'rememberme': 'on',
            'returnUrl': BASE_URL,
            'targetUrl': '',
        }
        resp = self.httpreq('post', 'login', data=login_body, allow_redirects=False)
        self.cookies = resp.cookies

    def post_bid(self, bid_info):
        self.login()
        resp_codeimg = self.httpreq('get', 'codeimg')
        with open(self._code_img, 'wb') as pf:
            pf.write(resp_codeimg.content)
        code = ocr_rec(self._code_img)

        body_data = {
                #'surplusAmount': int(bid_info['money'])*(100-int(bid_info['progress']))/100,
                #'security_session': self.cookies['JSESSIONID'],
                #'timestamp': int(time.time()),
            'code': code,
            'agree-contract': 'on',
            'loanId': bid_info['id'],
            'bidAmount': calc_bid_value(bid_info),
        }
        resp = self.httpreq('post', 'post', data=body_data)
        with codecs.open(os.path.join(self._err_html_dir, '%s.html' % (bid_info['id'])), 'w', encoding='utf8') as pf:
            pf.write(str(resp.headers))
            pf.write(resp.text)
        return True
        if self.success_string in resp.text:
            return True
        else:
            return False

class AutobidTest():
    def __init__(self):
        self.autobid = AutoBid()

    def test_ocr(self):
        resp_codeimg = self.autobid.httpreq('get', 'codeimg')
        with open(self.autobid._code_img, 'wb') as pf:
            pf.write(resp_codeimg.content)
        code = ocr_rec(self.autobid._code_img)
        print code


if __name__ == '__main__':
    import sys
    import time
    if len(sys.argv) == 2 and sys.argv[1] == 'debug':
        _debug = True
        # test ocr
        #t = AutobidTest()
        #t.test_ocr()
        #exit()

        auto_bid = AutoBid()
        auto_bid.money_available()
        exit(1)
        for i in range(1):
            auto_bid.find_bid()
            #auto_bid.login()
            #print auto_bid.cookies

    else:
        auto_bid = AutoBid()
        while True:
            print time.strftime('%Y-%m-%d %H:%M:%S')
            begin_t = time.time()
            try:
                auto_bid.execute()
            except SystemExit:
                exit()
            except:
                __import__('traceback').print_exc()
            end_t = time.time()
            print "execute time: (%s)\n" % (end_t - begin_t)
            time.sleep(10)



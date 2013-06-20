#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import requests
from lxml import etree
import yaml
import os
import webbrowser
from readbot import ReadBot
import sys

_debug = False

conf = yaml.load(open('config.yaml'))
header = {'user-agent': UA}
body = {
    'j_username': conf['username'],
    'j_password': conf['password'],
    'returnUrl': 'null',
    'targetUrl': '',
}

_keys = ('title', 'company', 'user', 'category', 'money', 'interest', 'months', 'progress')

_rrd_url = 'http://www.renrendai.com'
_rrd_url_login = os.path.join(_rrd_url, 'j_spring_security_check')
_rrd_url_loanlist = os.path.join(_rrd_url, 'lend', 'loanList.action') + '?id=all_biao_list'
_rrd_url_loadpage = os.path.join(_rrd_url, 'lend', 'detailPage.action') + '?loanId=%s'
_rrd_url_bidpage = os.path.join(_rrd_url, 'lend', 'bidPageAction.action') + '?loanId=%s'
_rrd_url_loanpost = os.path.join(_rrd_url, 'lend', 'loanLender.action')
_rrd_url_codeimg = os.path.join(_rrd_url, 'image.jsp')

def safe_mkdir(dir):
    if not os.path.isdir(dir):
        os.makedirs(dir)

_base_dir = '/tmp/rrd'
safe_mkdir(_base_dir)
_code_img = os.path.join(_base_dir, 'code.jpeg')
_code_img_back_dir = os.path.join(_base_dir, 'img')
safe_mkdir(_code_img_back_dir)
_err_html_dir = os.path.join(_base_dir, 'errhtml')
safe_mkdir(_err_html_dir)

bidlist_file = os.path.join(_base_dir, 'bidlist')
log_file = os.path.join(_base_dir, 'rrd.log')

_success_string = u'恭喜您，投标成功！'

def autobid():
    logprint('='*30, '')
    logprint(_debug, 'debug')
    # init cookies
    resp = httprequest('get', _rrd_url, headers=header)
    # login
    resp = httprequest('post', _rrd_url_login, data=body, headers=header, cookies=resp.cookies, allow_redirects=False)
    cookie = resp.cookies
    # 请求贷款列表
    resp = httprequest('get', _rrd_url_loanlist, headers=header, cookies=cookie)
    # 提取贷款信息
    page = etree.HTML(resp.text)
    hrefs = page.xpath(u'//div[@class="center biaoli"]')

    cookies = resp.cookies
    data = []
    for href in hrefs:
        i = 0
        d = {'id': href.get('id')}
        for t in href.itertext():
            t = t.strip()
            if t and t[0] == u'￥':
                # 如果text以￥开头，设置list 顺序为4
                # 防止前面某些项为空导致顺序混乱出错
                i = 4
            if t and i < len(_keys): # 超过keys长度的值不再处理
                # 格式化text的值
                k = _keys[i]
                if k == 'money':
                    t = t[1:].replace(',', '')
                elif k == 'interest':
                    t = t[:-1]
                elif k == 'months':
                    t = t[:-2]
                elif k == 'progress':
                    t = t[:-1]
                d[_keys[i]] = t
                i += 1
        data.append(d)
        # progress 字段值不是数字的处理(等待材料的情况)
        if not d['progress'].isdigit():
            continue
        if check_bid_worth(d):
            # should bid
            '''bid form:
            surplusAmount
            bidAmount 50
            security_session
            timestamp
            loanId
            '''
            loanid = d['id'][4:]
            if os.path.isfile(bidlist_file):
                bidlist = yaml.load(open(bidlist_file, 'r').read())
            else:
                bidlist = []
            if loanid not in bidlist:
                # 不在投资列表里，可以进行投资
                logprint('@'*30, '')
                logprint('begin bid...')
                logprint(loanid)

                #resp1 = requests.get(_rrd_url_bidpage % (loanid), headers=header, cookies=cookies)
                resp_codeimg = httprequest('get', _rrd_url_codeimg, headers=header, cookies=cookies)
                with open(_code_img, 'wb') as pf:
                    pf.write(resp_codeimg.content)

                code = ocr_rec(_code_img)

                body_data = {
                    'surplusAmount': int(d['money'])*(100-int(d['progress']))/100,
                    'bidAmount': calc_bid_value(d),
                    'security_session': cookies['JSESSIONID'],
                    'timestamp': int(time.time()),
                    'loanId': loanid,
                    'code': code,
                }
                resp = httprequest('post', _rrd_url_loanpost, data=body_data, headers=header, cookies=cookies)
                logprint(_success_string in resp.text)
                if _success_string in resp.text:
                    bidlist.append(loanid)
                    yaml.dump(bidlist, open(bidlist_file, 'w'))
                else:
                    with open(os.path.join(_err_html_dir, '%s.html' % (loanid)), 'w') as pf:
                        pf.write(resp.text.encode('utf8'))
                    #with open(os.path.join(_code_img_back_dir, '%s.jpeg' % (code)), 'wb') as pf:
                    #    pf.write(open(_code_img, 'rb').read())


            logstr = '%s|%s|%s|%s|%s' % (d['id'], d['title'], d['money'], d['interest'], d['months'])
            with open(log_file, 'a') as f:
                f.write(logstr.encode('utf8')+'\n')
            logprint(logstr)
            logprint('-'*30, '')
    logprint('+'*30, '')

def check_bid_worth(data):
    if float(data['interest']) >= 14 and int(data['progress']) < 100:
        return True
    else:
        return False

def calc_bid_value(data):
    if float(data['interest']) >= 18 and int(data['months']) <= 18:
        return 100
    else:
        return 50

def httprequest(method, url, *args, **kwargs):
    resp = requests.request(method, url, *args, **kwargs)
    if resp.status_code >=400:
        raise Exception('http can not response normally(%s)' % (resp.status_code))
    logprint(resp.cookies, 'debug')
    return resp

def toggle_open_browser(loadid):
    url = _rrd_url_loadpage % (loadid)
    webbrowser.open(url)

def ocr_rec(imgfile):
    rb = ReadBot()
    rb.ocr_config = ['digits']
    result = rb.interpret(imgfile)
    return result

def logprint(data, info_head='info'):
    if info_head:
        head_str = '[%s] ' % (info_head.upper())
    else:
        head_str = ''
    logstr = '%s%s' % (head_str, data)
    if not _debug and info_head.lower() == 'debug':
        return
    print logstr

if __name__ == '__main__':
    import time
    if len(sys.argv) == 2 and sys.argv[1] == 'debug':
        _debug = True
        autobid()
    else:
        while True:
            print time.strftime('%Y-%m-%d %H:%M:%S')
            begin_t = time.time()
            try:
                autobid()
            except SystemExit:
                exit()
            except:
                __import__('traceback').print_exc()
            end_t = time.time()
            print "execute time: (%s)\n" % (end_t - begin_t)
            time.sleep(20)



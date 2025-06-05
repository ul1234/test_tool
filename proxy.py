#!/usr/bin/python
# -*- coding: utf-8 -*-

import socket, threading, select, ctypes, sys, re, urllib.request
import winreg
from datetime import datetime

DEFAULT_PORT = 1234
HTTPVER = 'HTTP/1.1'

class HackHandler(object):
    STATUS_NONE = 0
    STATUS_BYPASS = 1

    def __init__(self):
        self.http_get_funcs = [getattr(self, f) for f in HackHandler.__dict__.keys() if f.startswith('_http_get') and not f.endswith('default')]
        self.http_get_funcs += [getattr(self, f) for f in HackHandler.__dict__.keys() if f.startswith('_http_get') and f.endswith('default')]

    def _redirect_to(self, new_url):
        content = '''
            <html>
            <head>
            <meta http-equiv="Refresh" content="0; url=%s" />
            </head>
            <body>
            </body>
            </html>''' % new_url
        print ('redirect to %s' % new_url)
        return HackHandler.STATUS_BYPASS, content

    def _html_body(self, body, head = ''):
        content = '''
            <html>
            %s
            <body>
            %s
            </body>
            </html>''' % (head, body)
        print ('populate html response')
        return HackHandler.STATUS_BYPASS, content

    def _html_head(self, content):
        content = '<head>%s</head>' % content
        return content

    def _html_css(self):
        css_content = '''
        <style type="text/css">
        table{
            border: 1px solid blue;
        }

        td, th{
            text-align: left;
            vertical-align: top;
            border-left: 1px solid blue;
            border-top: 1px solid blue;
        }

        th{
            border-right: 1px solid blue;
        }

        td.highlight{
            color:#7300AB;
            /*padding:1px 10px 1px 10px;*/
        }

        td.info{
            font-size: 12px;
            min-width: 600px;
            /*overflow:scroll;*/
        }

        .hdd{
            color: black;
            font-size: 20px;
            padding:1px 10px 1px 10px;
            /*width: 350px;*/
        }

        .PASS{
            color:#00FF00;
            font-size: 20px;
            text-align: left;
            vertical-align: top;
        }

        .FAIL{
            color:#FF0000;
            font-size: 20px;
            text-align: left;
            vertical-align: top;

        }

        .CRASH{
            color:#770000;
            font-size: 20px;
            text-align: left;
            vertical-align: top;
        }

        .INVALID{
            color:#BC8F8F;
            font-size: 20px;
            text-align: left;
            vertical-align: top;
        }

        .FATAL{
            color:#7300AB;
            font-size: 20px;
            text-align: left;
            vertical-align: top;
        }

        .COMMAND_ERROR {
            color:#3399FF;
            font-size: 20px;
            text-align: left;
            vertical-align: top;
        }

        .MISSING_RESOURCE {
            color:#F9621A;
            font-size: 20px;
            text-align: left;
            vertical-align: top;
        }
        </style>'''
        return css_content

    def _html_js_4(self):
        content = '''
            function add_link(){
                var table=document.getElementsByTagName('table')[0];
                table.setAttribute('id', 'change_table');
                var tds=table.getElementsByTagName('tr')[1].getElementsByTagName('td');
                var html='<br><br>[<a href="javascript:void(0);" onclick="show_all(this)">All</a>] [<a href="javascript:void(0);" onclick="show(this,show_run_hide)">Run</a>] [<a href="javascript:void(0);" onclick="show(this,show_fail_hide)">Fail</a>] [<a href="javascript:void(0);" onclick="show(this,show_crash_hide)">Crash</a>]';
                for(var i=1;i<tds.length;i++){
                    tds[i].insertAdjacentHTML("beforeEnd",html);
                }
            }

            var g_hidden_trs=new Array();
            function show_all(dom){
                if(g_hidden_trs.length>0){
                    for(var i=0;i<g_hidden_trs.length;i++){
                        g_hidden_trs[i].style.display='';
                    }
                    g_hidden_trs=[];
                }
            }
            function show_run_hide(text){
                if(text=='Not Run')return true;
                return false;
            }
            function show_fail_hide(text){
                if((text=='Not Run')||(text.indexOf('PASS')>=0&&text.indexOf('FAIL')<0&&text.indexOf('CRASH')<0))return true;
                return false;
            }
            function show_crash_hide(text){
                if(text.indexOf('CRASH')>=0)return false;
                return true;
            }
            function show(dom,hide_rule){
                var td=dom.parentNode;
                var index=0;
                while(td=td.previousSibling){
                    if(td.nodeName=='TD')index++;
                }
                var trs=document.getElementById('change_table').getElementsByTagName('tr');
                show_all(dom);
                for(var i=3;i<trs.length;i++){
                    if(hide_rule(trs[i].getElementsByTagName('td')[index].innerText)){
                        g_hidden_trs.push(trs[i]);
                    }
                }
                for(var i=0;i<g_hidden_trs.length;i++){
                    g_hidden_trs[i].style.display='none';
                }
            }
        '''
        return content

    def _html_js_5(self):
        content = '''
        <script>
        function show(dom,id){
            if(dom.innerHTML=='Hide'){
                dom.innerHTML='Details';
                document.getElementById(id).style.display="none";
            }
            else{
                dom.innerHTML='Hide';
                document.getElementById(id).style.display="block";
            }
        }
        </script>
        '''
        return content

    def hack(self, method, url):
        status, content = HackHandler.STATUS_NONE, None
        if method == 'GET':
            for func in self.http_get_funcs:
                result = func(url)
                if not result is None: return result
        return status, content

    def _urlopen(self, url):
        content = None
        try_times = 3
        for i in range(try_times):
            try:
                content = urllib.request.urlopen(url, timeout = 10).read()
                break
            except Exception as e:
                if i < (try_times-1): print ('Exception [%d]:' % (i+1), e, ',', url)
        if content is None: raise Exception('Exception [%d]: fail to retrieve %s' % (try_times, url))
        return content

    def _http_get_ukrav_default(self, url):
        # http://ukrav/results/get_result_rav_bubble.php
        if url.startswith(r'http://ukrav/results/get_result_rav_bubble.php'):
            content = self._urlopen(url)
            return self._html_body(content)
        return None

    def _http_get_ukrav_history_1(self, url):
        # http://ukrav/results/history_plot.php?table=lte-plat-c-tdd3gpp&branch=ALL&var=ALL&tnum=82808
        # http://ukrav/results/full_test_history.php?page=lte_3gpp_fdd_platc_cue&test_number=32891
        r = re.search(r'http://ukrav/results/history_plot\.php\?table=([^&]+)&.*tnum=(\d+)$', url)
        if r:
            product, test_case = r.group(1), r.group(2)
            new_url = 'http://ukrav/results/full_test_history.php?page=%s&test_number=%s' % (product, test_case)
            return self._redirect_to(new_url)
        return None

    def _http_get_ukrav_history_2(self, url):
        # http://ukrav/results/full_test_history.php?page=lte-plat-c-tdd3gpp&test_number=90169
        r = re.search(r'http://ukrav/results/full_test_history\.php\?page=([^&]+)&test_number=(\d+)$', url)
        if r:
            product, test_case = r.group(1), r.group(2)
            content = self._urlopen(url)
            ### 1. add a new column "All Info"
            virtual_url = r'http://ukrav/results/get_result_rav.php?t=%s&tnum=%s' % (product, test_case)
            content = content.replace('<td>Result</td>', "<td>Result</td><td><a href=%s>All Info</a></td>" % virtual_url)
            ### 2. populate the column for each row
            # http://ukrav/results/get_result_rav.php?t=lte-plat-c-tdd3gpp&trun=RAV31_15_01_21_18_57&tnum=90169
            add_url = r'http://ukrav/results/get_result_rav.php?t=%s&trun=\2&tnum=%s' % (product, test_case)
            replace_part = r"\1\3<a href='%s'>INFO</a></td>\4" % add_url
            content = re.sub(r'(<tr><td>.*?</td><td>.*?</td><td>(.*?)</td>(<td[^<>]+>).*?</td>)(</tr>)', replace_part, content)
            return self._html_body(content)
        return None

    def _thread_get_info(self, info_url, lock, sem, index, content, head):
        #print ('url', url)
        build_label, url = info_url
        with sem:
            with lock: print ('retrieve  ', url)
            info = self._urlopen(url)
        with lock:
            if not head:
                r = re.search(r'<head>.*</head>', info, flags = re.DOTALL)
                if r: head.append(r.group(0))
            pos = info.find(r'<body>')
            info = info[pos+6:]
            replace_part = r'\1<br> Build Label:%s,%s\2\3' % (build_label, '&nbsp;'*5)
            info = re.sub(r'(<br><p.*?>).*?<br>.*?<br>\s*(Test run:.*?</p>)<br><br>(<table[\w\W]*?</table>)[\w\W]*$', replace_part, info)
            if pos >= 0:
                content.append((index, info))
            else:
                print ('ERROR: no <body> found in ', url)

    def _http_get_ukrav_history_3(self, url):
        # http://ukrav/results/get_result_rav.php?t=%s&tnum=%s
        # this is a totally virtual url
        MAX_HISTORY_INFO_NUM = 10
        r = re.search(r'http://ukrav/results/get_result_rav\.php\?t=([^&]+)&tnum=(\d+)$', url)
        if r:
            product, test_case = r.group(1), r.group(2)
            history_url = r'http://ukrav/results/full_test_history.php?page=%s&test_number=%s' % (product, test_case)
            content = self._urlopen(history_url)
            info_url_pattern = r'http://ukrav/results/get_result_rav.php?t=%s&trun=%s&tnum=%s'
            info_urls = []
            for r in re.finditer(r"<tr><td>([^<]*?)</td><td>.*?</td><td>([^<]*?)</td><td class='(\w+)'>.*?</td></tr>", content):
                info_url = info_url_pattern % (product, r.group(2), test_case)
                build_label = r.group(1)
                #print ('add', r.group(3), info_url)
                if r.group(3).lower() != 'pass':
                    info_urls.append((build_label, info_url))
            if len(info_urls) > MAX_HISTORY_INFO_NUM: info_urls = info_urls[-MAX_HISTORY_INFO_NUM:]
            content, head, threads = [], [], []
            sem = threading.Semaphore(5)  # max 5 url get
            lock = threading.Lock()
            for index, info_url in enumerate(info_urls):
                threads.append(threading.Thread(target = self._thread_get_info, args = (info_url, lock, sem, index, content, head)))
            for t in threads: t.start()
            for t in threads: t.join()
            content.sort()
            content = reduce(lambda a,b: a+b, [c for i, c in content], '')
            return self._html_body(content, head[0] if head else '')
        return None

    def _http_get_ukrav_history_4(self, url):
        # http://ukrav/results/tables_30.php?page=lte_3gpp_fdd_platc_cue
        # http://ukrav/results/tables_30_filter.php?page=lte_3gpp_fdd_platc_cue&var=-LS2-
        r = re.search(r'http://ukrav/results/tables_30(_filter)?\.php\?page=', url)
        if r:
            content = self._urlopen(url)
            ### 1. remove bubble
            #content = content.replace(r'onMouseOver="bubble(this);" onmouseout="return nd();"', ' ')
            content = content.replace('<td class=\'PASS\'><a  onMouseOver="bubble(this);" onmouseout="return nd();"', '<td class=\'PASS\'><a  ')
            ### 2. change Not Run link
            # <td class='Not Run'><a href='#'>Not Run</a></td>
            content = content.replace(r"<a href='#'>Not Run</a>", 'Not Run')
            ### 3. remove Notes tag after history
            # [<a href='issue_track.php?build=MDAwMDhfU05NUF9XYWxrX3Rlc3QudHh0@@lte_3gpp_fdd_platc_cue' class='notes_link' rel='facebox'>Notes</a>]
            content = re.sub(r'\[<a\s+href=[^>]*>Notes</a>\]', ' ', content)
            ### 4. change history link url address
            # [<a href='history_plot.php?table=lte-plat-c-tdd3gpp&branch=ALL&var=ALL&tnum=82808' target='_blank'>History</a>]
            # [<a href='full_test_history.php?page=lte_3gpp_fdd_platc_cue&test_number=32891' target='_blank'>History</a>]
            replace_part = r'\1full_test_history.php?page=\2&test_number=\3\4'
            content = re.sub(r"(\[<a\s+href=')history_plot\.php\?table=([^&]+)&.*tnum=(\d+)('[^>]*>History</a>\])", replace_part, content)
            ### 5. change javascript
            js = self._html_js_4()
            content = re.sub(r'(<script>\s*jQuery\(document\)\.ready[\w\W]*?)\}\)(\s*</script>)', r'\1add_link();})\n%s\2' % js, content)
            return self._html_body(content)
        return None

    def _thread_get_rav_summary(self, lock, sem, url, all_case_info = {}):
        with sem:
            with lock: print ('retrieve  ', url)
            content = self._urlopen(url)
        for r in re.finditer(r'data\.setCell\(\d+,\s*0,\D+(\d{5})[^\)]+\);\s*data\.setCell\(\d+,\s*1,[^;]*?(file:[^>]*.html)>(\d{5}_[^<]+)<[^;]+\);[^;]*;\s*data\.setCell\(\d+,\s*3,[^;]*?<span[^>]+>(.*?)</[^;]*\);', content):
            case_num, file_link, case_name, info = r.group(1), r.group(2), r.group(3), r.group(4)
            if info.find('<br>') < 0:
                # 13:01:56.4190 xxx
                info = re.sub(r'(\d{2}:\d{2}:\d{2}\.\d{4})', r'<br>\1', info)[4:]  # remove the first <br>
            if case_num in all_case_info: raise Exception('identical case num %s, %s' % (case_num, case_name))
            all_case_info[case_num] = (case_name, file_link, info)
        with lock: print ('retrieve info ok from %s' % url)

    def _http_get_ukrav_history_5(self, url):
        # http://ukrav/results/summary_plot.php?table=lte_3gpp_fdd_platc_cue&trun=RAV52_15_02_24_18_24
        r = re.search(r'(http://ukrav/results/summary_plot\.php\?table=([^&]+)&trun=)([^&]+)$', url)
        if r:
            summary_part_url, product, rav_run = r.group(1), r.group(2), r.group(3)
            # http://ukrav/results/tables_30.php?page=lte_3gpp_fdd_platc_cue
            info_url = r'http://ukrav/results/tables_30.php?page=%s' % product
            print ('retrieve ', info_url)
            content = self._urlopen(info_url)
            content = content.replace('<br>', '\n')
            ### 1. remove Notes and History tag
            # [<a href='history_plot.php?table=lte_3gpp_fdd_platc_cue&branch=ALL&var=ALL&tnum=30113' target='_blank'>History</a>]
            # [<a href='issue_track.php?build=MDAwMDhfU05NUF9XYWxrX3Rlc3QudHh0@@lte_3gpp_fdd_platc_cue' class='notes_link' rel='facebox'>Notes</a>]
            content = re.sub(r'\[<a\s+href=[^>]*>(History|Notes)</a>\]', ' ', content)
            table_list = []
            for r in re.finditer(r'<tr>(<td.*?>(<a.*?>)?[^<>]*?(</a>)?</td>)+</tr>', content):
                # 30113_3GPP_PDCP_5MHz_UL_POWER_CAPPING_PUSCH_VERIFY_N.txt
                items = re.findall(r'(?<=(?<!/a)>)[^<>]*?(?=(?:</a>)?</td>)', r.group(0))
                if len(items) > 1: table_list.append(items)
            table_head = table_list.pop(0)
            remove_lines = [table_list.pop(0)] + [table_list.pop(-1)] + [table_list.pop(-1)] + [table_list.pop(-1)]  # summary line and last 3 lines
            for remove_line in remove_lines:
                if re.search(r'^\d{5}', remove_line[0].strip()): raise Exception('remove line error: %s' % remove_line)
            remove_index = [row for row, c in enumerate(table_list) if c[0].startswith('00') or c[0].startswith('48')]
            for i in remove_index[::-1]: table_list.pop(i)  # remove '00xxx' and '48xxx'
            summary_urls = {}
            process_index = 0
            for i, head in enumerate(table_head):
                if i == 0: continue
                build, rav_label, test_rav_run, _ = head.split('\n')
                summary_urls[test_rav_run] = summary_part_url + test_rav_run
                if test_rav_run == rav_run:
                    assert process_index == 0, 'find more than 1 results for %s' % rav_run
                    process_index = i
            assert process_index > 0, 'cannot find results for %s' % rav_run
            # retrieve all summary info for all RAV run
            all_info = {}
            threads = []
            sem = threading.Semaphore(5)  # max 5 url get
            lock = threading.Lock()
            for rav_run, summary_url in summary_urls.items():
                all_info[rav_run] = {}
                threads.append(threading.Thread(target = self._thread_get_rav_summary, args = (lock, sem, summary_url, all_info[rav_run])))
            for t in threads: t.start()
            for t in threads: t.join()
            print ('all summary info retrieved')
            #####  retrieve end ##################
            table = zip(*tuple(table_list))
            cases, result = table[0], table[process_index]
            candidates = ['PASS', 'FAIL', 'FATAL', 'INVALID', 'CRASH', 'COMMAND_ERROR', 'MISSING_RESOURCE', 'Not Run']
            num, rows = {}, {}
            rows['Other'] = []
            num['Total'] = len(result)
            num['Unknown'] = 0
            for c in candidates:
                num[c] = 0
                rows[c] = []
            for index, r in enumerate(result):
                found = False
                for c in candidates:
                    if r.find(c) >= 0:
                        num[c] += 1
                        found = True
                        if c in ['FAIL', 'FATAL', 'CRASH']:
                            rows[c].append(index)
                        elif c not in ['PASS', 'Not Run']:
                            rows['Other'].append(index)
                        break
                if not found:
                    num['Unknown'] += 1
                    print ('Unknown: %s, %s' % (cases[index], r))
            html_content = self._html_summarize(num)
            rows['SameAsToT'] = []
            for rslt in ['CRASH', 'FAIL', 'FATAL', 'Other']:
                remove_list = []
                for row in rows[rslt]:
                    if self._same_fail_as_tot_or_platform_issue(table_head, table_list[row], process_index, all_info):
                        print ('same as tot,', table_list[row][0].split('\n'))
                        remove_list.append(row)
                rows['SameAsToT'] += remove_list
                for r in remove_list: rows[rslt].remove(r)
            #result_rows = [row for row, c in enumerate(result) if c not in ['PASS', 'Not Run']]
            for rslt in ['CRASH', 'FAIL', 'FATAL', 'Other', 'SameAsToT']:
                html_content += '<p class="hdd">%s: %d [<a href="javascript:void(0);" onclick="show(this, \'table_%s\')";>Hide</a>]</p>' % (rslt, len(rows[rslt]), rslt)
                html_content += '<div id="table_%s">' % rslt
                for row in rows[rslt]:
                    html_content += self._html_one_case(product, table_head, table_list[row], process_index, all_info)
                    html_content += '<p />'
                html_content += '</div>'
            return self._html_body(html_content, head = self._html_head(self._html_css()+self._html_js_5()))
        return None

    def _html_summarize(self, num):
        run_num = num['Total'] - num['Not Run']
        fail_num = num['FAIL'] + num['FATAL']
        other_num = run_num - fail_num - num['PASS'] - num['CRASH']
        if not num['Total']: num['Total'] = 1
        if not run_num: run_num = 1
        content = '<p align="center" class = "hdd">Total: %d, Run: %d, Coverage: %.1f%%<br>' % (num['Total'], run_num, 100.0*run_num/num['Total'])
        content += 'Pass: %d (%.1f%%), Crash: %d (%.1f%%), Fail(and Fatal): %d (%.1f%%), Other: %d (%.1f%%)</p>' % (num['PASS'], 100.0*num['PASS']/run_num,
                    num['CRASH'], 100.0*num['CRASH']/run_num, fail_num, 100.0*fail_num/run_num, other_num, 100.0*other_num/run_num)
        return content

    def _platform_issue(self, run_info):
        platform_msg = [r'The RF hardware fitted does not support the specified carrier frequencies',
                        r'Capture_IQ_CaptMem: ERROR',
                        r'FAIL: Data Captured',
                        r'Socket Error : [Errno 10060] A connection attempt failed']
        for info in run_info:
            for msg in platform_msg:
                if info.find(msg) >= 0:
                    return True
        return False

    def _same_fail_as_tot_or_platform_issue(self, table_head, case_result, process_index, all_info = {}):
        def _info_silimar(info1, info2, threshold = 75):      # 75% similarity
            if not info1 or not info2: return False
            if len(info1) != len(info2): return False
            for i1, i2 in zip(info1, info2):
                if not StrTool.similar(i1, i2, threshold = threshold): return False
            return True
        # all_info[rav_run][case_num]: (case_name, file_link, info)
        # case_result: table row
        results = [(table_head[i], case_result[i], True if i == process_index else False) for i, r in enumerate(case_result) if r != 'Not Run']
        case = results[0][1].strip()
        case_num = case[:5]

        history_result = []
        run_version = None
        for i, r in enumerate(case_result):
            if r != 'Not Run' and i > 0:
                version, rav_label, rav_run, _ = table_head[i].split('\n')
                fail = case_result[i]
                info = all_info[rav_run][case_num][2].split('<br>') if rav_run in all_info and case_num in all_info[rav_run] else []
                if i == process_index:
                    run_version, run_fail, run_info = version, fail, info
                else:
                    history_result.append((version, fail, info))
        if self._platform_issue(run_info): return True  # platform issue, remove the fail log
        assert run_version, 'no version found, index %s.' % process_index
        if not history_result: return False
        tot_history_result = [(version, fail, info) for version, fail, info in history_result if version and '0' <= version[-1] <= '9'] # tot version, not a private version
        threshold = max(len(tot_history_result)/2, 2)
        similar_num = 0
        remain_num = len(tot_history_result)
        for version, fail, info in tot_history_result:
            remain_num -= 1
            if run_fail == fail and _info_silimar(run_info, info):
                similar_num += 1
                if similar_num >= threshold: # similar result >= 1/2, at least 2
                    return True
                elif (similar_num + remain_num) < threshold:
                    return False
        return False

    def _html_one_case(self, product, table_head, case_result, process_index, all_info = {}, max_result_num = 5):
        # all_info[rav_run][case_num]: (case_name, file_link, info)
        # case_result: table row
        results = [(table_head[i], case_result[i], True if i == process_index else False) for i, r in enumerate(case_result) if r != 'Not Run']
        case = results[0][1].strip()
        case_num = case[:5]
        result_table = ''
        for r in results[:0:-1]:
            head, rslt, highlight = r
            build, rav_label, rav_run, _ = head.split('\n')
            highlight_class = info_highlight = highlight_id = info_str = ''
            if highlight:
                highlight_class = ' class="highlight"'
                info_highlight = ' highlight'
                highlight_id = ' id="%s"' % case_num
            rslt_str = rslt
            if rav_run in all_info and case_num in all_info[rav_run]:
                case_name, file_link, info_str = all_info[rav_run][case_num]
                file_link = file_link.replace('\\\\', '\\')
                rslt_str = '<a href="%s" class="%s">%s</a>' % (file_link, rslt, rslt)
                if case.find(case_name) < 0: print ('case name not the same, %s, %s' % (case, case_name))
            result_table += '<tr%s><td%s>%s</td><td%s>%s</td><td class="%s">%s</td><td class="info%s">%s</td></tr>' % (highlight_id, highlight_class, build, highlight_class, rav_run, rslt, rslt_str, info_highlight, info_str)
        # [<a href='full_test_history.php?page=lte_3gpp_fdd_platc_cue&test_number=32891' target='_blank'>History</a>]
        content = r'<table><tr><th colspan=4>%s [<a href="full_test_history.php?page=%s&test_number=%s">History</a>] [<a href="#%s">To Case</a>]</th></tr>%s</table>' % (case, product, case_num, case_num, result_table)
        return content

    def no_http_get_tsms(self, url):
        r = re.search(r'http://tsms/?(.*/now)?$', url)
        if r:
            new_url = 'http://tsms/calander=%s/' % '-'.join([str(int(x)) for x in datetime.now().strftime('%Y-%m-%d').split('-')])
            return self._redirect_to(new_url)
        return None

class ConnectionHandler(object):
    BUFLEN = 8192

    def __init__(self, connection, address, timeout, hack_handler = None):
        self.client = connection
        self.client_buffer = ''
        self.timeout = timeout
        self.hack_handler = hack_handler
        self.target = None
        try:
            self.method, self.path, self.protocol = self.get_base_header()
            if self.hack_handler:
                status, content = self.hack_handler.hack(self.method, self.path)
                if status == HackHandler.STATUS_BYPASS:
                    self.client.send(content)
                else:
                    if self.method == 'CONNECT':
                        self.method_CONNECT()
                    elif self.method in ('OPTIONS', 'GET', 'HEAD', 'POST', 'PUT',
                                         'DELETE', 'TRACE'):
                        self.method_others()
        except Exception as e:
            print (e)
        self.client.close()
        if self.target: self.target.close()

    def get_base_header(self):
        while True:
            self.client_buffer += self.client.recv(ConnectionHandler.BUFLEN)
            end = self.client_buffer.find('\n')
            if end != -1:
                break
        print ('%s' % self.client_buffer[:end])     # debug
        data = (self.client_buffer[:end+1]).split()
        self.client_buffer = self.client_buffer[end+1:]
        return data

    def method_CONNECT(self):
        self._connect_target(self.path)
        self.client.send(HTTPVER+' 200 Connection established\n'+
                         'Proxy-agent: Python Proxy\n\n')
        self.client_buffer = ''
        self._read_write()

    def method_others(self):
        self.path = self.path[7:]
        i = self.path.find('/')
        host = self.path[:i]
        path = self.path[i:]
        self._connect_target(host)
        self.target.send('%s %s %s\n'%(self.method, path, self.protocol)+
                         self.client_buffer)
        self.client_buffer = ''
        self._read_write()

    def _connect_target(self, host):
        i = host.find(':')
        if i!=-1:
            port = int(host[i+1:])
            host = host[:i]
        else:
            port = 80
        (soc_family, _, _, _, address) = socket.getaddrinfo(host, port)[0]
        self.target = socket.socket(soc_family)
        self.target.connect(address)

    def _read_write(self):
        time_out_max = self.timeout/3
        socs = [self.client, self.target]
        count = 0
        while True:
            count += 1
            (recv, _, error) = select.select(socs, [], socs, 3)
            if error:
                break
            if recv:
                for in_ in recv:
                    data = in_.recv(ConnectionHandler.BUFLEN)
                    if in_ is self.client:
                        out = self.target
                    else:
                        out = self.client
                    if data:
                        out.send(data)
                        count = 0
            if count == time_out_max:
                break

class ProxyServer(object):
    def __init__(self, server_socket, handler = ConnectionHandler, timeout = 60, hack_handler = None):
        self.server_socket = server_socket
        self.handler = handler
        self.timeout = timeout
        self.hack_handler = hack_handler
        self.disable_urllib.request_proxy()

    def serve_forever(self):
        soc = socket.socket(socket.AF_INET)
        soc.bind(self.server_socket)
        print ("Serving on %s:%d..." % self.server_socket)
        soc.listen(0)
        while True:
            threading.Thread(target = self.handler, args = soc.accept()+(self.timeout, self.hack_handler)).start()

    def disable_urllib2_proxy(self):
        #proxy_handler = urllib.request.ProxyHandler({"http":"http://127.0.0.1:1234"})
        proxy_handler = urllib.request.ProxyHandler({})  # no http proxy in urllib.request
        opener = urllib.request.build_opener(proxy_handler)
        urllib.request.install_opener(opener)


class Registry(object):
    def set_key(self, key_location, key_path, name, value):
        reg_key = winreg.OpenKey(key_location, key_path, 0, winreg.KEY_ALL_ACCESS)
        try:
            _, reg_type = winreg.QueryValueEx(reg_key, name)
        except WindowsError:
            # If the value does not exists yet, we guess use a string as the reg_type
            reg_type = winreg.REG_SZ
        winreg.SetValueEx(reg_key, name, 0, reg_type, value)
        winreg.CloseKey(reg_key)

    def delete_key(self, key_location, key_path, name):
        reg_key = winreg.OpenKey(key_location, key_path, 0, winreg.KEY_ALL_ACCESS)
        try:
            winreg.DeleteValue(reg_key, name)
        except WindowsError:
            # Ignores if the key value doesn't exists
            pass
        winreg.CloseKey(reg_key)


class WindowsProxySetting(object):
    # See http://msdn.microsoft.com/en-us/library/aa385328(v=vs.85).aspx
    INTERNET_OPTION_REFRESH = 37
    INTERNET_OPTION_SETTINGS_CHANGED = 39

    def __init__(self):
        self.proxy_reg_key_location = winreg.HKEY_CURRENT_USER
        self.proxy_reg_key_path = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
        self.internet_set_option = ctypes.windll.Wininet.InternetSetOptionW
        self.reg = Registry()

    def _set_proxy_key(self, name, value):
        self.reg.set_key(self.proxy_reg_key_location, self.proxy_reg_key_path, name, value)

    def _refresh(self):
        self.internet_set_option(0, self.INTERNET_OPTION_REFRESH, 0, 0)
        self.internet_set_option(0, self.INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)

    def enable_proxy(self, proxy, bypass = ''):
        self._set_proxy_key('ProxyEnable', 1)
        #self._set_proxy_key('ProxyOverride', u'*.local;<local>')  # Bypass the proxy for localhost
        self._set_proxy_key('ProxyOverride', bypass)
        self._set_proxy_key('ProxyServer', proxy)
        self._refresh()

    def disable_proxy(self):
        self._set_proxy_key('ProxyEnable', 0)
        self._refresh()

class StrTool:
    @staticmethod
    def similar(str1, str2, threshold = 75):
        max_len = max(len(str1), len(str2))
        if not max_len: return True
        similar_value = (1 - StrTool.distance(str1, str2) / float(max_len)) * 100
        return similar_value >= threshold
        #return (similar_value >= threshold, round(similar_value, 2))

    @staticmethod
    def distance(str1, str2):
        # levenshtein distance
        if len(str1) == 0: return len(str2)
        elif len(str2) == 0: return len(str1)
        short_str, long_str = (str2, str1) if len(str1) > len(str2) else (str1, str2)
        rows, cols = len(short_str) + 1,  len(long_str) + 1
        matrix = [range(cols) for x in range(rows)]
        #print (matrix)
        for i in range(1,rows):
            for j in range(1,cols):
                deletion = matrix[i-1][j] + 1
                insertion = matrix[i][j-1] + 1
                substitution = matrix[i-1][j-1]
                if short_str[i-1] != long_str[j-1]:
                    substitution += 1
                matrix[i][j] = min(insertion, deletion, substitution)
        #print (matrix)
        return matrix[rows-1][cols-1]


if __name__ == "__main__":
    setting = WindowsProxySetting()
    # python proxy.py {start|stop} remote proxy [bypass]
    # python proxy.py {start|stop} [local] [port] [nohack]
    action = 'start' if len(sys.argv) <= 1 else sys.argv[1]
    type = 'local' if len(sys.argv) <= 2 else sys.argv[2]
    if type == 'local':
        port = DEFAULT_PORT if len(sys.argv) <= 3 else int(sys.argv[3])
        nohack = False if len(sys.argv) <= 4 or sys.argv[4] != 'nohack' else True
    elif type == 'remote':
        remote_proxy = None if len(sys.argv) <= 3 else sys.argv[3]
        bypass = '' if len(sys.argv) <= 4 else sys.argv[4]
        if not remote_proxy: raise Exception('no proxy setting in remote mode.')
    else:
        raise Exception('Usage: python proxy.py {start|stop} {local|remote} [port] [nohack]')

    if action != 'start':
        setting.disable_proxy()
    else:
        if type == 'remote':
            setting.enable_proxy(remote_proxy, bypass)
        else:  # 'local'
            local_proxy = 'localhost:%d' % port
            setting.enable_proxy(local_proxy)
            hack_handler = None if nohack else HackHandler()
            server = ProxyServer(('localhost', port), hack_handler = hack_handler)
            server.serve_forever()

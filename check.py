#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys, os, re


class CodeCheck(object):
    CHECK_RULES = ['indent', 'space']

    def __init__(self):
        self.rule = Rule()

    def check(self, files, log_file):
        with open(log_file, 'w') as f_write:
            for f in files:
                results = self.check_file(f)
                if results:
                    f_write.write('[%s] FAIL\n' % f)
                    for r in results:
                        f_write.write('    %s\n' % r[1])
                    f_write.write('\n')
                else:
                    f_write.write('[%s] PASS\n\n' % f)

    def check_file(self, filename):
        with open(filename, 'r') as f:
            lines = f.readlines()
            results = []
            for i, line in enumerate(lines):
                result = self.rule_check(line, i)
                if isinstance(result, tuple) and not result[0]:
                    results.append(result)
        return results

    def rule_check(self, line, line_index, context = None):
        for r in self.CHECK_RULES:
            if hasattr(self.rule, 'rule_%s' % r):
                f = getattr(self.rule, 'rule_%s' % r)
                result = f(line, context)
                if isinstance(result, tuple):
                    result_f, result_msg = result
                    if not result_f: return False, '[line %d] %s' % (line_index+1, result_msg)
        return True


class Rule(object):
    INDENT_SPACES = 3

    def __init__(self):
        pass
        
    def update_context(self, line):
        pass

    def rule_indent(self, line, context = None):
        if not line.strip(): return True
        if not context or context.type not in ['f_comments', 'f_params']:
            first_char = line.strip()[0]
            leading_spaces = line.find(first_char)
            return True if (leading_spaces % self.INDENT_SPACES) == 0 else False, 'incorrect leading spaces %d' % leading_spaces
        return True

    def _except_space(self, sym, line, context = None):
        def except_include(sym, line): return line.find('#include') > -1
        _excepts = {('<', '>'): except_include}
        for ex, f in _excepts.items():
            if not isinstance(ex, tuple): ex = (ex)
            if sym in ex and f(sym, line): return True
        return False
        
    def rule_space(self, line, context = None):
        error_msg = 'lack of space on position %d'
        if not line.strip(): return True
        sym_type_1 = ['==', '>=', '<=', '<', '!=', '+=', '-=', '*=', '/=', '&&', '||']  # type 1, space before and after the symbol
        regx_type_1 = [r'(?<![\+\*-/><!=])=(?!=)', r'(?<!-)>', r'(?<!&)&(?!&)', r'(?<!|)|(?!|)']
        sym_type_2 = [',', ';']   # space after the symbol, or the end of the line
        line = line.strip()
        def check_type_1(line, pos, s):
            if pos > -1:
                if pos > 0 and line[pos-1] != ' ': return False, error_msg % (pos+1)
                if len(line) > (pos+len(s)) and line[pos+len(s)] != ' ': return False, error_msg % (pos+1)
                return True
        def check_type_2(line, pos, s):
            if pos > -1:
                if len(line) > (pos+len(s)) and line[pos+len(s)] != ' ': return False, error_msg % (pos+1)
                return True
        for s in sym_type_1:
            result = check_type_1(line, line.find(s), s)
            if isinstance(result, tuple) and not result[0] and not self._except_space(s, line): return result
        for s in regx_type_1:
            r = re.search(s, line)
            if r:
                pos = r.span()[0]
                result = check_type_1(line, pos, s)
            if isinstance(result, tuple) and not result[0] and not self._except_space(s, line): return result
        for s in sym_type_2:
            result = check_type_2(line, line.find(s), s)
            if isinstance(result, tuple) and not result[0] and not self._except_space(s, line): return result


if __name__ == '__main__':
    select = 1



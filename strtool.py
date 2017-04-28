#!/usr/bin/python
# -*- coding: utf-8 -*-

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
        #print matrix
        for i in range(1,rows):
            for j in range(1,cols):
                deletion = matrix[i-1][j] + 1
                insertion = matrix[i][j-1] + 1
                substitution = matrix[i-1][j-1]
                if short_str[i-1] != long_str[j-1]:
                    substitution += 1
                matrix[i][j] = min(insertion, deletion, substitution)
        #print matrix
        return matrix[rows-1][cols-1]

if __name__ == "__main__":
    print StrTool.similar('abbbbbbba','abbbbbbbb')
    print StrTool.similar('abc','abe')
    print StrTool.similar('aabc','abe')
    print StrTool.similar('abca','abeefff')
    print StrTool.similar("TTMRUNNER: FAIL: UE0: Channel DL-SCH (Codeword: 0), ['BLER'] is NOT in range 0.9114 - 0.99 (it is ('UE0: ', 'DL-SCH (Codeword: 0)', ['BLER'], [0.91139999999999999, 0.98999999999999999], 0.99166666670000003))",
                            "TTMRUNNER: FAIL: UE0: Channel DL-SCH (Codeword: 0), ['BLER'] is NOT in range 0.9114 - 0.99 (it is ('UE0: ', 'DL-SCH (Codeword: 0)', ['BLER'], [0.91139999999999999, 0.98999999999999999], 0.99594059410000002))")
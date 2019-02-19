####################################################################################################################
工具集合:

1. log 分析
    1) gen_log 命令, 批量用loganalyse.exe 从dat转log 文件
    2) split_files 命令, 批量拆分log 文件
    3) search 命令, 批量从一堆log文件中搜索第一个出现的某个特征字段
    4) filter 命令, 从一堆log文件中寻找某个特征字段, 把所有的匹配行加上周围几行一起过滤输出到某个文件

2. teamcity 工具
    1) presub 命令, 一键提交 NR5G的 presub 
    2) sanity 命令, 一键运行checkin 所需要的sanity batches
    
3. HDE 脚本
    1) script 命令, 从case的运行结果html文件中, 转换成 HDE所需要运行的脚本

####################################################################################################################
工具用法:

1. 在英国机器上，开一个windows command 窗口
2. 输入 python \\ltn3-eud-nas01\data\SHA2\swang2\tools\test_tool.py 回车
3. 在 (Cmd) 提示符后输入相应命令即可

####################################################################################################################
命令说明:

1. 综合说明
    1) 所有的命令都可以用 help <command> 来看该命令的具体参数说明及用法

       例子: 
            help sanity
            help filter
            
        比较长的命令一般都有缩写, 缩写与命令本身等价, 比如 help gen_log 会显示  Usage: gen_log(glog) [-0] [-p path] [-d] [-o] [-z] [-f] {files(regex)}
        其中 glog 是 gen_log 的缩写, 两个用起来没有区别

    2) 参数中带(regex)说明的是匹配, 基本所有的匹配 (文件匹配 和 字段匹配) 都可以用正则表达式 (这样功能更强大, 灵活), 开始加 @字符, 代表后面是正则表达式

        最最常用的用法是: 点星 .* 匹配任意字符
        例子: 文件夹中的 log 文件有 MUX_1.dat, MUX_2.dat, MUX_12.dat, 则匹配所有文件为 MUX.*dat, 或MUX, 都行
        
    3) 下面的每个命令的例子都是最常用的用法, 其他可以通过参数的改动的部分可以用help 查看

2. 所有命令

    1) gen_log 命令, 批量用loganalyse.exe 从dat转log 文件

        1> 首先需要把log文件对应的loganalyse.exe, loganalyse.dll, tm500defs.dll，拷贝到log文件存放的目录

        例子:
            glog -p E:\30.Temp\1\190130_151231_Logs\190130_151231_Logs @MUX.*dat
            转换E:\30.Temp\1\190130_151231_Logs\190130_151231_Logs目录下的所有满足 MUX.*dat 正则匹配的log 文件, @不能省, 代表后面是正则表达式

    2) split_files 命令, 批量拆分log 文件

        例子:
            spl -p E:\30.Temp\1\190130_151231_Logs\190130_151231_Logs @MUX.*hlc.txt
            拆分E:\30.Temp\1\190130_151231_Logs\190130_151231_Logs目录下的所有满足 MUX.*hlc.txt 正则匹配的文件, 默认每个文件按30M大小拆分, 保留前中后各一个文件
            通过更改参数可以改变拆出来的文件大小, 个数等        

    3) search 命令, 批量从一堆log文件中搜索第一个出现的某个特征字段

        例子: 
            search -p E:\30.Temp\1\190130_151231_Logs\190130_151231_Logs @MUX.*txt -r LOG_NR_L0_DLC_PDCCH_CTRL_CNFG_ADD_CELL
            在E:\30.Temp\1\190130_151231_Logs\190130_151231_Logs目录下的所有满足MUX.*txt正则匹配的文件, 寻找包含匹配LOG_NR_L0_DLC_PDCCH_CTRL_CNFG_ADD_CELL的行,
            找到后屏幕上输出找到的文件, 如果文件太大, 会自动拆解文件

    4) filter 命令, 从一堆log文件中寻找某个特征字段, 把所有的匹配行加上周围几行一起过滤输出到某个文件

        例子:
            filter -p D:\30.Temp\1\190130_151231_Logs\190130_151231_Logs @mux.*txt -r ADD_UE
            在E:\30.Temp\1\190130_151231_Logs\190130_151231_Logs目录下的所有满足mux.*txt正则匹配的文件, 寻找所有包含匹配ADD_UE的行, 找到后连同该行前后各3行(可通过参数改),
            输出到输出文件, 默认输出文件为 filter_result.txt
            
    5) presub 命令, 一键提交 NR5G的 presub

        1> 运行前需要配置一个动态view, 默认为 Z: 盘, 如果不是Z:盘需要在命令里用参数设置动态view的盘符, 动态view的目的是利用动态view可以快速提交presub, 这是Hongwei发现的
        
        例子:
            presub D:\Projects\swang2_view_cue_tot_feature_2
            一键提交NR5G的presub, 利用Z:的动态view, 可以节省几次点击及等待时间
            
            presub D:\Projects\swang2_view_cue_tot_feature_2 -v X:
            一键提交NR5G的presub, 利用X:的动态view, 如果动态view不是Z:, 需要用-v参数后面跟盘符
            
    6) sanity 命令, 一键运行checkin 所需要的sanity batches

        例子:
            sanity D:\Projects\swang2_view_cue_tot_feature_2
            一键提交三个remote run, 分别是 1 cell basic batch, 15k+120k 1cell batch, 2cell batch, 提交三次, 1cell的分开提交两次, 主要是哪个batch结果不完美可以重新跑
            
    7) script 命令, 从case的运行结果html文件中, 转换成 HDE所需要运行的脚本

        例子:
            script C:\aa\99904_NR5G_PDCP_TEST_20181026-10-03-30.html -o C:\bb
            从 C:\aa\99904_NR5G_PDCP_TEST_20181026-10-03-30.html 文件中生成HDE需要的脚本, 输出到 C:\bb文件夹中

import os
import re
import xml.etree.ElementTree as ET

class gnbLog:
    def __init__(self):
        pass
        
    def extract_data_from_file(self, xml_file):
        tree = ET.parse(xml_file)
        root = tree.getroot()

        ns = {'ns': ''}  # XML无命名空间，简化处理

        msg_header = root.find(".//msgHeader")      # 当前节点下所有子孙节点中查找msgHeader
        utc_high = msg_header.find("utcHigh").attrib.get("VALUE")
        utc_low = msg_header.find("utcLow").attrib.get("VALUE")

        cell_handle = root.find(".//cellHandle").attrib.get("VALUE")

        data_lines = []

        # 处理 dlSatelliteConfig 和 ulSatelliteConfig
        for sat_type, dl_flag in [("dlSatelliteConfig", "1"), ("ulSatelliteConfig", "0")]:
            config = root.find(f".//cellSatelliteConfig/{sat_type}/delayDopplerConfigList")
            if config is not None:
                for index in config.findall("INDEX"):
                    start_delay = index.find("startDelay").attrib.get("VALUE")
                    delay_rate = index.find("delayChangeRate").attrib.get("VALUE")
                    start_doppler = index.find("startDoppler").attrib.get("VALUE")
                    doppler_rate = index.find("dopplerChangeRate").attrib.get("VALUE")

                    start_time = index.find("startTime")
                    super_sfn = start_time.find("superSfn").attrib.get("VALUE")
                    sfn = start_time.find("sfn").attrib.get("VALUE")
                    sf = start_time.find("sf").attrib.get("VALUE")

                    line = f"{utc_high}, {utc_low}, {cell_handle}, {dl_flag}, {super_sfn}, {sfn}, {sf}, {start_delay}, {delay_rate}, {start_doppler}, {doppler_rate}"
                    data_lines.append(line)

        return data_lines

    def process_folder(self, files_list, output_file):
        all_lines = []
        for filename in files_list:
            lines = extract_data_from_file(filename)
            all_lines.extend(lines)

        with open(output_file, "w") as f:
            for line in all_lines:
                f.write(line + "\n")

        #print(f"合并完成，共生成 {len(all_lines)} 行，输出文件为: {output_file}")

# 修改为你的文件夹路径
#xml_folder = "D:/08.Test/Log/signaling/signaling_XML_2025-06-04_0723"
#output_txt = "merged_output.txt"



if __name__ == '__main__':
    if len(sys.argv) <= 2:
        print("Usage: python gnb_log.py {xml_files} {output_file} \n")
        exit()
    process_folder(sys.argv[1], sys.argv[2])

import os
import re
import xml.etree.ElementTree as ET

class gnbLog:
    def __init__(self):
        pass
        
    def extract_delay_doppler_req(self, xml_file):
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

                    line = f"{utc_high:>9}, {utc_low:>10}, {cell_handle:>5}, {dl_flag:>5}, {super_sfn:>9}, {sfn:>4}, {sf:>2}, {start_delay:>12}, {delay_rate:>12}, {start_doppler:>12}, {doppler_rate:>12}"
                    data_lines.append(line)

        return data_lines

    def process_delay_doppler_req(self, files_list, output_file):
        all_lines = []
        for filename in files_list:
            lines = self.extract_delay_doppler_req(filename)
            all_lines.extend(lines)

        with open(output_file, "w") as f:
            utc_high, utc_low, cell_handle, dl_flag, super_sfn, sfn, sf, start_delay, delay_rate, start_doppler, doppler_rate = \
                "utc_high", "utc_low", "cell", "dl", "super_sfn", "sfn", "sf", "start_delay", "delay_rate", "start_doppler", "doppler_rate"
            f.write(f"{utc_high:>9}, {utc_low:>10}, {cell_handle:>5}, {dl_flag:>5}, {super_sfn:>9}, {sfn:>4}, {sf:>2}, {start_delay:>12}, {delay_rate:>12}, {start_doppler:>12}, {doppler_rate:>12}\n")
            for line in all_lines:
                f.write(line + "\n")

    def extract_sib19_req(self, xml_file):
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

                    line = f"{utc_high:>9}, {utc_low:>10}, {cell_handle:>5}, {dl_flag:>5}, {super_sfn:>9}, {sfn:>4}, {sf:>2}, {start_delay:>12}, {delay_rate:>12}, {start_doppler:>12}, {doppler_rate:>12}"
                    data_lines.append(line)

        return data_lines


if __name__ == '__main__':
    if len(sys.argv) <= 2:
        print("Usage: python gnb_log.py {xml_files} {output_file} \n")
        exit()
    process_folder(sys.argv[1], sys.argv[2])

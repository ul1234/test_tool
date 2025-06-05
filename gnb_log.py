import os
import re
import xml.etree.ElementTree as ET

class gnbLog:
    def __init__(self):
        self.extract_func_list = [("CrrcDelayDopplerConfig_Req", self.extract_delay_doppler_req),
            ("CrrcNtnSibUpdateConfig_Req_SIB19", self.extract_sib19_req)]

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

                    line = f"utc_high: {utc_high:>9}, utc_low: {utc_low:>10}, cell: {cell_handle:>1}, dl: {dl_flag:>1}, ssfn: {super_sfn:>9}, sfn: {sfn:>4}, sf: {sf:>2}, start_delay: {start_delay:>10}, delay_rate: {delay_rate:>10}, start_doppler: {start_doppler:>10}, doppler_rate: {doppler_rate:>10}"
                    data_lines.append(line)
        return data_lines

    def extract_func(self, filename):
        for pattern, func in self.extract_func_list:
            if re.search(pattern, filename, flags = re.IGNORECASE):
                return func
        print (f"cannot find func for {filename}\n")
        return None

    def process(self, files_list, output_file):
        all_lines = []
        for filename in files_list:
            # detect file type
            func = self.extract_func(filename)
            if func:
                lines = func(filename)
                all_lines.extend(lines)
        if all_lines:
            with open(output_file, "w") as f:
                for line in all_lines:
                    f.write(line + "\n")
            return True
        else:
            return False

    def extract_sib19_req(self, xml_file):
        tree = ET.parse(xml_file)
        root = tree.getroot()

        ns = {'ns': ''}  # XML无命名空间，简化处理

        msg_header = root.find(".//msgHeader")      # 当前节点下所有子孙节点中查找msgHeader
        utc_high = msg_header.find("utcHigh").attrib.get("VALUE")
        utc_low = msg_header.find("utcLow").attrib.get("VALUE")

        cell_handle = root.find(".//cellHandle").attrib.get("VALUE")

        data_lines = []

        config = root.find(".//sib19ConfigList")
        if config is not None:
            for index in config.findall("INDEX"):
                ntn_config = index.find(".//ntn_Config_r17")
                epoch_sfn = ntn_config.find(".//sfn_r17").attrib.get("VALUE")
                epoch_sf = ntn_config.find(".//subFrameNR_r17").attrib.get("VALUE")
                ul_valid_duration = ntn_config.find(".//ntn_UlSyncValidityDuration_r17").attrib.get("VALUE")
                k_offset_cell = ntn_config.find(".//cellSpecificKoffset_r17").attrib.get("VALUE")
                ta_common = ntn_config.find(".//ta_Common_r17").attrib.get("VALUE")
                ta_common_drift = ntn_config.find(".//ta_CommonDrift_r17").attrib.get("VALUE")
                ta_common_drift_variant = ntn_config.find(".//ta_CommonDriftVariant_r17").attrib.get("VALUE")
                position_x = ntn_config.find(".//positionX_r17").attrib.get("VALUE")
                position_y = ntn_config.find(".//positionY_r17").attrib.get("VALUE")
                position_z = ntn_config.find(".//positionZ_r17").attrib.get("VALUE")
                velocity_x = ntn_config.find(".//velocityVX_r17").attrib.get("VALUE")
                velocity_y = ntn_config.find(".//velocityVY_r17").attrib.get("VALUE")
                velocity_z = ntn_config.find(".//velocityVZ_r17").attrib.get("VALUE")

                line = f"utc_high: {utc_high:>9}, utc_low: {utc_low:>10}, cell: {cell_handle:>1}, epoch_sfn: {epoch_sfn:>4}, epoch_sf: {epoch_sf:>2}, ul_valid_duration: {ul_valid_duration:>2}, k_offset_cell: {k_offset_cell:>3}, ta_common: {ta_common:>8}, ta_common_drift: {ta_common_drift:>2}, ta_common_drift_variant: {ta_common_drift_variant:>2}, position_x: {position_x:>9}, position_y: {position_y:>9}, position_z: {position_z:>3}, velocity_x: {velocity_x:>8}, velocity_y: {velocity_y:>8}, velocity_z: {velocity_z:>3}"
                data_lines.append(line)
        return data_lines


if __name__ == '__main__':
    if len(sys.argv) <= 2:
        print("Usage: python gnb_log.py {xml_files} {output_file} \n")
        exit()
    process_folder(sys.argv[1], sys.argv[2])

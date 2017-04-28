
# small log functions can be used
ul_mac_payload = [
    'LOG_UL_BRP_MAC_PAYLOAD_MSG_PARAMS',
    'LOG_UL_BRP_MAC_PAYLOAD_MSG_DATAPDU',           # L1 -> ul_brp data, every TTI
    ]

ul_ctrl_config = [
    'LOG_UL_CTRL_RX_CPHY_CELL_PARAMS_BASE',         # L1-> ul_ctrl, ul cell params, usually once at system startup
    'LOG_UL_CTRL_RX_CONFIG_MSG_BASE',               # L1-> ul_ctrl, ul ue params, usually once at system startup
    ]

ul_ctrl_mac_info = [
    'LOG_UL_CTRL_RX_UL_SCH_DATA_READY_RSP_BASE',    # L1 -> ul_ctrl, ul info, every TTI
    ]

ul_brp_data = [
    'LOG_UL_BRP_BASE_ENC_MESSAGE',                  # ul_ctrl -> ul_brp, encode info
    'LOG_UL_BRP_BASE_SRP_MESSAGES',                 # ul_brp -> ul_srp data
    ]

ul_srp_data = [
    'LOG_UL_CTRL_SLAVE_UL_SRP_MAIN_MSG_BASE',       # ul_ctrl -> ul_srp, tti config info, in ul_ctrl_slave
    'LOG_UL_SRP_BASE_PUSCH_TTI',                    # ul_ctrl -> ul_srp, tti config info
    'LOG_UL_SRP_BASE_RX_TICK_RATE',                 # ul_srp -> UMBRA data, every TTI
    ]

ul_pucch_clash = [
    'LOG_UL_SRP_PUCCH_BASE_COPRO_MSG_RX',
    ]

# log functions
ul_crc = [
    ul_mac_payload,
    ul_ctrl_config,
    ul_ctrl_mac_info,
    ul_brp_data,
    ul_srp_data,
    ]

ul_cqi = [
    ]

ul_harq = [
    ]

import aiosqlite
from loguru import logger

LAB_DEFINITIONS = [
    ("LAB-01", "Get Started with Cisco CLI",                     "CLI & Basic"),
    ("LAB-02", "Switching Operation",                            "CLI & Basic"),
    ("LAB-03", "Basic Configuration",                            "CLI & Basic"),
    ("LAB-04", "Password Recovery on Router",                    "CLI & Basic"),
    ("LAB-05", "Backup and Restore Configuration",               "CLI & Basic"),
    ("LAB-06", "Cisco Discovery Protocol (CDP)",                 "Switching & VLAN"),
    ("LAB-07", "VLAN and Trunking",                              "Switching & VLAN"),
    ("LAB-08", "Manual VLAN Pruning",                            "Switching & VLAN"),
    ("LAB-09", "Trunk Native VLAN",                              "Switching & VLAN"),
    ("LAB-10", "Voice VLAN",                                     "Switching & VLAN"),
    ("LAB-11", "Dynamic Trunking Protocol (DTP)",                "Switching & VLAN"),
    ("LAB-12", "Rapid PVST+",                                    "Switching & VLAN"),
    ("LAB-13", "Enhance STP Features with PortFast",             "Switching & VLAN"),
    ("LAB-14", "Enhance STP Features with Rootguard",            "Switching & VLAN"),
    ("LAB-15", "Enhance STP Features with BPDU Guard",           "Switching & VLAN"),
    ("LAB-16", "L2 Loop Test",                                   "Switching & VLAN"),
    ("LAB-17", "Layer 2 EtherChannel",                           "Switching & VLAN"),
    ("LAB-18", "Basic Wireless LAN Controller (WLC)",            "Wireless"),
    ("LAB-19", "Inter-VLAN with Router on a Stick (ROAS)",       "Inter-VLAN & Routing"),
    ("LAB-20", "Inter-VLAN with Switch Virtual Interface (SVI)", "Inter-VLAN & Routing"),
    ("LAB-21", "IPv4 Static and Default Route",                  "Inter-VLAN & Routing"),
    ("LAB-22", "IPv6 Static and Default Route",                  "Inter-VLAN & Routing"),
    ("LAB-23", "OSPFv2 Single Area",                             "Inter-VLAN & Routing"),
    ("LAB-24", "OSPFv2 Multi Area",                              "Inter-VLAN & Routing"),
    ("LAB-25", "OSPFv2 Network Type",                            "Inter-VLAN & Routing"),
    ("LAB-26", "OSPFv2 Summarization",                           "Inter-VLAN & Routing"),
    ("LAB-27", "OSPFv2 Default-information originate",           "Inter-VLAN & Routing"),
    ("LAB-28", "OSPFv2 Authentication",                          "Inter-VLAN & Routing"),
    ("LAB-29", "OSPFv2 Path Optimization",                       "Inter-VLAN & Routing"),
    ("LAB-30", "OSPFv3 for IPv6",                                "Inter-VLAN & Routing"),
    ("LAB-31", "IPv4 HSRP on Router",                            "HSRP & ACL"),
    ("LAB-32", "IPv4 HSRP on Switch",                            "HSRP & ACL"),
    ("LAB-33", "IPv4 Numbered ACL",                              "HSRP & ACL"),
    ("LAB-34", "Add Remark for IPv4 ACL",                        "HSRP & ACL"),
    ("LAB-35", "IPv4 Named ACL",                                 "HSRP & ACL"),
    ("LAB-36", "Implement Static NAT",                           "NAT & DHCP"),
    ("LAB-37", "Implement Dynamic NAT",                          "NAT & DHCP"),
    ("LAB-38", "Implement NAT Overloading (PAT)",                "NAT & DHCP"),
    ("LAB-39", "DHCP Server on Cisco IOS",                       "NAT & DHCP"),
    ("LAB-40", "DHCP Relay on Cisco IOS",                        "NAT & DHCP"),
    ("LAB-41", "DHCP Client on Cisco IOS",                       "NAT & DHCP"),
    ("LAB-42", "Network Time Protocol (NTP)",                    "Management"),
    ("LAB-43", "Syslog",                                         "Management"),
    ("LAB-44", "SNMP",                                           "Management"),
    ("LAB-45", "Netflow",                                        "Management"),
    ("LAB-46", "Enable SSH on Cisco IOS",                        "Management"),
    ("LAB-47", "Site-to-Site VPN with GRE",                      "Security & Advanced"),
    ("LAB-48", "Port Security",                                   "Security & Advanced"),
    ("LAB-49", "DHCP Snooping",                                  "Security & Advanced"),
    ("LAB-50", "Upgrade IOS on Router",                          "Security & Advanced"),
    ("LAB-51", "Network Controller",                             "Security & Advanced"),
]

async def seed_labs(db: aiosqlite.Connection) -> None:
    logger.bind(name="db").info(
        f"Seeding {len(LAB_DEFINITIONS)} labs (metadata only - file_path stays NULL until import)..."
    )
    try:
        for lab_id, name, category in LAB_DEFINITIONS:
            await db.execute(
                "INSERT OR IGNORE INTO labs (id, name, category) VALUES (?,?,?)",
                (lab_id, name, category)
            )
            await db.execute(
                "INSERT OR IGNORE INTO progress (lab_id) VALUES (?)",
                (lab_id,)
            )
        await db.commit()
        logger.bind(name="db").success(f"Seeded {len(LAB_DEFINITIONS)} labs.")
    except Exception:
        await db.rollback()
        logger.bind(name="db").exception("seed_labs failed; rolled back")
        raise

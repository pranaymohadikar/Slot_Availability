"""
roles.py - manual coach_id -> role mapping.

HOW TO USE
  Change the value (right of the colon) for each coach to ONE of:
      "Nutritionist"  |  "Physiotherapist"  |  "Psychologist"
  Leave doctors / anyone outside those three as "Other".
  The UUID key is what the pipeline matches on; the name after # is just for reference.
  Any coach NOT listed here falls back to "Other" automatically.

  Used by pipeline.py:  slots_df["role"] = slots_df["health_coach_id"].map(ROLE_BY_ID).fillna("Other")
"""

ROLE_BY_ID = {

    "1ef78bbe-89fa-11ef-b39a-000d3a3e18d5": "Nutritionist",      # Bhakti Bhavsar
    "e12cd4b4-7fee-11ef-b39a-000d3a3e18d5": "Nutritionist",      # Bhumika Shah
    "50466c4e-246e-11ee-a67f-f4ce2d75c16b": "Nutritionist",      # Bhuvaneshwari Savant
    "657875f4-8789-11ee-9b73-8fadb27840d6": "Psychologist",      # Dr. Himval Pandya
    "4882bf99-50b0-11ef-8ea0-000d3a3e18d5": "Physiotherapist",      # Dr. Iswarya V
    "784ebfe3-d155-11ee-b31f-68258013e02a": "Physiotherapist",      # Dr. Jiwangi Singh

    "90bbc1e3-c46e-11f0-9722-000d3a3e18d5": "Psychologist",      # Manya Jain
    "4c0444f0-0ee2-11f0-a17d-000d3a3e18d5": "Nutritionist",      # Michelle Christopher
    "9fdd7be7-9da9-11ee-9b73-8fadb27840d6": "Physiotherapist",      # Nisheshilka Singh

    "c380b410-3dba-11ef-8ea0-000d3a3e18d5": "Nutritionist",      # Radhika Rao
    "91ef31c8-21e2-11f1-86d9-000d3a3e18d5": "Physiotherapist",      # Reema Bhuva

    "d797816d-caac-11f0-9722-000d3a3e18d5": "Physiotherapist",      # Sakshi Vaidya
    "6b509d97-df23-11f0-9722-000d3a3e18d5": "Psychologist",      # Shobika KR
    "d945499c-5d80-11f0-bf53-000d3a3e18d5": "Psychologist",      # Shubha Dubey
    "3e952ad2-69e1-11ef-b39a-000d3a3e18d5": "Psychologist",      # Sridurga R
    "9f952cc4-6dfa-11f0-bf53-000d3a3e18d5": "Nutritionist",      # Swetha Kshirsagar
    "83196674-0ee4-11f0-a17d-000d3a3e18d5": "Other",      # Tejaswini Rao Gudati
    "fa0d6f97-a81d-11f0-a0bb-000d3a3e18d5": "Nutritionist",      # Vandna Lalchandani

}
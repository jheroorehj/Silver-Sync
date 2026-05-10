import pandas as pd

files = [
    "./data_csv/의약품안전사용서비스(DUR)_노인주의 품목리스트 2025.6.csv",
    "./data_csv/의약품안전사용서비스(DUR)_노인주의(해열진통소염제) 품목리스트 2025.6.csv",
    "./data_csv/Elderly_Caution_Full_Mapping_HTN_DM.csv",
    "./data_csv/DUR_HTN_DM_Consolidated_Mapping.csv"
]

for f in files:
    try:
        try:
            df = pd.read_csv(f, encoding="utf-8", low_memory=False)
        except UnicodeDecodeError:
            df = pd.read_csv(f, encoding="cp949", low_memory=False)
        print(f"{f}")
        print(f"  행 수: {len(df)}행")
        print(f"  컬럼: {df.columns.tolist()}\n")
    except Exception as e:
        print(f"  오류: {e}")
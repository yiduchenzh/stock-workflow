from strategies.chan_theory import _detect_divergence, _detect_hub
from data.sources import get_kline

df = get_kline('000001', 120)
hubs = _detect_hub(df)
divs = _detect_divergence(df, hubs)
print('Hubs:', len(hubs))
print('Divergences:', len(divs))
for d in divs:
    print(f'  {d["type"]}: {d["position"]} (strength={d.get("strength","n/a")})')
    if d["type"] == "rsi_divergence":
        print(f'    RSI: {d.get("rsi_current","?")} vs prev {d.get("rsi_previous","?")}')
    elif d["type"] == "volume_divergence":
        print(f'    price={d.get("price_trend","?")}, vol={d.get("volume_trend","?")}')

# 보관: 운영자·기관 화면 (2026-11-21 사이트에서 내림)

2026-11-21 밤 기획 변경(주인 결정)으로 기관용 서비스를 사이트에서 뺐다. 화면 코드는 여기에 그대로 보관하고,
화면이 쓰던 데이터(`web/data/*.json`)와 계산 스크립트(`scripts/`)는 저장소에 그대로 둔다.

- `operator.html` — 원래 `web/operator.html`
- `assets/operator.js`, `live_exit.js`, `audience_car.js`, `data_quality.js` — 원래 `web/assets/`
- 다시 살리려면 네 파일과 html을 `web/`로 되돌리고, `scripts/check_all.py`의 id 검사 쌍과 `docs/design.md` 4절 목록을 복구한다.
  html은 `assets/common.js`, `map3d.js`, `visitor.js`, `style.css`도 쓴다(이것들은 관객 화면과 함께 `web/assets/`에 남아 있음).

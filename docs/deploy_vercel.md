# Vercel에 올리기 (실시간 중계 서버 + 웹앱)

## 구조
- `web/` 웹 화면 (관객 index.html, 운영자 operator.html)
- `api/parking.js` → `/api/parking` : 올림픽공원 주차 합계 + 송파·강동 공영주차장 빈자리 (2분 공유)
- `api/roads.js` → `/api/roads` : 도로 58구간, 근처 주차장, 지하철 도착, 날씨 (3분 공유)
- `api/drive.js` → `/api/drive` : 출발지 → 주차장 운전 시간 (네이버, 선택. 1km 격자·15분 공유)
- `vercel.json` : web 폴더를 사이트로, api 폴더를 서버 함수로

## 처음 한 번
1. GitHub Desktop에서 olpark-traffic 을 Commit → Push
2. vercel.com → Add New → Project → olpark-traffic 저장소 Import
3. Framework Preset: Other (나머지는 그대로)
4. Environment Variables:
   - `SEOUL_API_KEY` = 서울 열린데이터광장 인증키 (필수)
   - `NAVER_KEY_ID`, `NAVER_KEY` = 네이버 클라우드 Maps 키 (선택)
5. Deploy → 생기는 주소(예: olpark-traffic.vercel.app)로 접속

## 이후
GitHub에 Push할 때마다 자동으로 다시 배포된다.

## 확인
- `주소/api/parking` 을 열면 JSON이 보여야 한다. `error`가 보이면 환경변수를 확인.
- 화면 아래 "실시간: ..." 문구가 보이면 연결된 것.

## 호출 수 (무료 한도 관리)
응답을 Vercel이 2~3분(운전 시간은 15분) 저장해서 모든 사용자에게 같이 준다.
관객 수와 관계없이 서울시 API 호출은 하루 최대 약 2,000~3,000번 수준.

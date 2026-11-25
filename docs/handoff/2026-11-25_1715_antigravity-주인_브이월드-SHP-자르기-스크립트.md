# 브이월드 대용량 SHP 압축파일(GIS건물통합정보·등고선) 올림픽공원 반경 추출 스크립트 추가

- 날짜·시각: 2026-11-25 17:15
- 누가: antigravity-주인
- 관련 Issue/PR: 없음

## 요청 해석
- 주인이 브이월드 `공간정보 다운로드`에서 내려받은 `GIS건물통합정보`(134MB)와 `등고선`(73MB) 파일이 너무 커서 채팅창 업로드 및 GitHub(100MB 제한) 직접 반영이 불가능하므로, 별도 GIS 프로그램이나 외부 패키지 설치 없이 로컬에서 더블클릭 한 번으로 올림픽공원 주변만 가볍게 잘라(`GeoJSON` 1~2MB 수준) 추출하는 스크립트를 만든다.

## 바꾼 것
- `scripts/35_clip_vworld_shp.py` (신규):
  - 파이썬 표준 라이브러리(`zipfile`, `struct`, `math`, `json`)만 사용해 `.zip` 압축을 풀지 않고 스트리밍으로 읽으며, `[선택다운로드]`로 받은 중첩 `.zip`도 자동 처리한다.
  - `.prj` WKT 및 헤더 범위를 해석해 `EPSG:5174`(베셀 구 중부원점 + 10.405초 가산경도 + 국토지리정보원 7변수 타원체 변환), `EPSG:5186`, `EPSG:5181`, `EPSG:5179`(UTM-K), `EPSG:5178`, `EPSG:4326` 좌표를 `WGS84` 경위도로 정확히 변환한다.
  - 올림픽공원·주변 역 반경(`127.103~127.142, 37.504~37.530`) 바깥 레코드는 36바이트 경계상자 단계에서 즉시 건너뛰고, 긴 등고선은 Liang-Barsky 선분 클리핑으로 범위 안쪽만 남긴다.
  - 인자 없이 실행하면 `data/raw/`, 프로젝트 루트, 윈도우 `Downloads`/`Desktop` 폴더에서 최근 받은 브이월드 `.zip`을 자동 탐색하고, 못 찾으면 파일 선택창(`tkinter`)을 띄운다.
  - 결과는 `data/processed/vworld_buildings_olpark.geojson`(건물 높이 `height_m` 포함) 및 `data/processed/vworld_contours_olpark.geojson`(표고 `elev_m` 포함)으로 저장한다.
- `run_clip_vworld.bat` (신규): 더블클릭 실행 및 `.zip` 파일 드래그 앤 드롭(`%*`)을 모두 지원하는 윈도우 실행 파일.

## 확인한 방법
- 합성 검증 데이터(`EPSG:5174` 구멍 있는 건물 Polygon + CP949 한글 속성 `A9/A12/A16`, 중첩 `.zip` 안의 `EPSG:5186` 장거리 등고선 PolyLine `CONT`)를 만들어 `python3 scripts/35_clip_vworld_shp.py` 실행 → 좌표 오차 0.1m 이내, 외곽/구멍 링 분리, 경계상자 선분 클리핑, `height_m`·`elev_m` 추출 정상 동작 확인.
- `python3 scripts/check_all.py` → ❌ 0건 통과.

## 결정과 이유
- 주인 컴퓨터에 `geopandas`·`pyproj`·`QGIS`가 없어도 바로 돌아가야 하므로 외부 의존성 0개(순수 표준 라이브러리)로 작성했다.
- 브이월드 구형 `EPSG:5174` `.prj` 파일에 흔히 누락되는 가산경도(`10.405"` = `0.00289028°`)와 7변수 변환(`BESSEL_TOWGS84`)을 자동 보정해 건물이 약 300m 어긋나는 문제를 예방했다.

## 건드리면 안 되는 것
- `scripts/35_clip_vworld_shp.py`의 `BESSEL_TOWGS84` 및 `127.0028902777778` 보정식(빼면 `EPSG:5174` 건물이 남동쪽으로 약 310m 밀림).

## 다음 사람에게 넘길 일
- 주인 컴퓨터에서 `git pull` 후 `run_clip_vworld.bat` 실행 → 생성된 `data/processed/vworld_buildings_olpark.geojson`과 `data/processed/vworld_contours_olpark.geojson`을 받아 3D 정적 건물 높이 및 보행망 경사도 반영 예정.

/**
 * 올팍 AI 오케스트라 — 구글 시트 작업함 연결 스크립트
 *
 * 팀원은 구글 시트 '작업함' 탭에 할 일을 한 줄씩 적고, 오케스트라(orchestra.bat → 8번)가
 * 이 스크립트를 통해 '대기' 줄을 가져가 AI에게 맡긴 뒤 상태·PR 링크·Codex 판정을 다시 적는다.
 *
 * 설치 (시트 주인이 한 번만):
 *   1) 시트 메뉴 [확장 프로그램] → [Apps Script] → 기본 코드를 지우고 이 파일 내용을 붙여 넣고 저장
 *   2) 위쪽 함수 고르기에서 setup 을 골라 [실행] → 권한 허용 → 아래 [실행 로그]에 나온 '오케스트라 토큰'을 복사
 *   3) [배포] → [새 배포] → 유형 '웹 앱' → 실행 사용자 '나', 액세스 권한 '모든 사용자' → [배포] → 웹 앱 URL 복사
 *   4) 오케스트라를 돌리는 컴퓨터에서 set_keys.bat 실행 → 웹 앱 URL과 토큰을 붙여 넣기
 *      (토큰은 채팅·문서에 올리지 않는다. 토큰을 아는 사람만 이 시트의 상태를 바꿀 수 있다.)
 *
 * 열(1행 머리글, 이름이 정확히 같아야 함):
 *   번호 | 요청자 | 할 일 | 자세한 내용 | 종류 | 상태 | 결과(PR) | Codex 판정 | 갱신 시각
 *   종류: 자동(비워 두면 자동) / 코딩 / 디자인
 *   상태: 비워 두거나 '대기'면 가져감 → 진행중 → 완료 / 수정필요 / 실패  (사람이 '보류'로 바꾸면 안 가져감)
 */
const SHEET_NAME = '작업함';
const HEAD = ['번호', '요청자', '할 일', '자세한 내용', '종류', '상태', '결과(PR)', 'Codex 판정', '갱신 시각'];

function setup() {
  const p = PropertiesService.getScriptProperties();
  let t = p.getProperty('TOKEN');
  if (!t) {
    t = Utilities.getUuid().replace(/-/g, '') + Utilities.getUuid().replace(/-/g, '').slice(0, 8);
    p.setProperty('TOKEN', t);
  }
  Logger.log('오케스트라 토큰: ' + t);
}

function sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return ss.getSheetByName(SHEET_NAME) || ss.getSheets()[0];
}

function cols_(sh) {
  const h = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map((x) => String(x).trim());
  const m = {};
  HEAD.forEach((k) => {
    const i = h.indexOf(k);
    if (i < 0) throw new Error('머리글이 없어요: ' + k);
    m[k] = i + 1;
  });
  return m;
}

function out_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

function auth_(t) {
  const want = PropertiesService.getScriptProperties().getProperty('TOKEN');
  return !!want && t === want;
}

// 대기 중인 할 일 목록
function doGet(e) {
  if (!auth_(e.parameter.token)) return out_({ error: '토큰이 맞지 않아요' });
  const sh = sheet_();
  const c = cols_(sh);
  const n = sh.getLastRow();
  if (n < 2) return out_({ tasks: [] });
  const v = sh.getRange(2, 1, n - 1, sh.getLastColumn()).getValues();
  const tasks = [];
  v.forEach((r, i) => {
    const title = String(r[c['할 일'] - 1]).trim();
    const st = String(r[c['상태'] - 1]).trim();
    if (title && (st === '' || st === '대기')) {
      tasks.push({
        row: i + 2, no: String(r[c['번호'] - 1]), who: String(r[c['요청자'] - 1]),
        title: title, detail: String(r[c['자세한 내용'] - 1]), kind: String(r[c['종류'] - 1]).trim(),
      });
    }
  });
  return out_({ tasks: tasks });
}

// 상태 바꾸기. action=claim 이면 아직 '대기'일 때만 '진행중'으로 바꾼다(두 컴퓨터가 같은 일을 잡지 않게).
function doPost(e) {
  const b = JSON.parse((e.postData && e.postData.contents) || '{}');
  if (!auth_(b.token)) return out_({ error: '토큰이 맞지 않아요' });
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const sh = sheet_();
    const c = cols_(sh);
    const row = Number(b.row);
    if (!(row >= 2)) return out_({ error: '줄 번호가 이상해요' });
    const cur = String(sh.getRange(row, c['상태']).getValue()).trim();
    if (b.action === 'claim' && cur !== '' && cur !== '대기') return out_({ ok: false, status: cur });
    if (b.status) sh.getRange(row, c['상태']).setValue(b.status);
    if (b.result !== undefined) sh.getRange(row, c['결과(PR)']).setValue(b.result);
    if (b.verdict !== undefined) sh.getRange(row, c['Codex 판정']).setValue(b.verdict);
    sh.getRange(row, c['갱신 시각']).setValue(Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm'));
    return out_({ ok: true });
  } finally {
    lock.releaseLock();
  }
}

// 단계 전환만 담당한다. 원래 데이터·추천·GPS 모듈의 id와 이벤트는 유지한다.
(() => {
  const $ = (id) => document.getElementById(id);
  let step = 'event';
  let mapReturn = 'topics';
  let transition;
  const titles = {
    event: '공연 선택', mode: '이동수단 선택', parking: '주차 위치 선택',
    direction: '이동 방면 선택', guide: '출구별 귀가 안내', transit: '대중교통 안내',
    topics: '안내 선택', map: '주변 도로와 도보 경로',
  };
  const previous = {mode: 'event', topics: 'mode', parking: 'topics', direction: 'parking', guide: 'direction', transit: 'mode'};
  function summary() {
    const text = $('event').selectedOptions[0]?.textContent || '';
    const match = text.match(/^(\d{1,2}:\d{2})\s+(.+?)\s+·\s+(.+)$/);
    $('journeyEvent').textContent = match ? match[3] : text;
    $('journeyMeta').textContent = match ? `${$('date').value.replaceAll('-', '.')} · ${match[1]} · ${match[2]}` : '';
  }
  function show(n, focus = true, direction = 1) {
    transition?.cancel();
    step = n;
    const car = ['parking', 'direction', 'guide'].includes(n);
    const result = n === 'guide' || n === 'transit' || n === 'map';
    document.querySelectorAll('[data-journey]').forEach(el => {
      const key = el.dataset.journey;
      el.hidden = !(key === n || (key === 'car' && car) || (key === 'result' && result));
    });
    document.querySelectorAll('[data-car]').forEach(el => {
      el.hidden = el.dataset.car !== n;
    });
    $('journeyBack').hidden = n === 'event';
    $('journeySelection').hidden = n === 'event';
    $('journeyTitle').textContent = titles[n];
    summary();
    if (n === 'map') window.dispatchEvent(new Event('resize'));
    if (focus) {
      $('journeyTitle').focus({preventScroll:true});
      window.scrollTo({top:0,behavior:'instant'});
      if ($('journeyMain').animate && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        transition = $('journeyMain').animate([
          {opacity: .65, transform: `translateX(${direction * 12}px)`},
          {opacity: 1, transform: 'translateX(0)'},
        ], {duration: 210, easing: 'ease-out'});
      }
    }
  }
  function list() {
    const box = $('journeyShows');
    box.replaceChildren();
    [...$('event').options].forEach(option => {
      const m = option.textContent.match(/^(\d{1,2}:\d{2})\s+(.+?)\s+·\s+(.+)$/);
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'show-choice';
      const venue = document.createElement('span'); venue.className = 'show-venue'; venue.textContent = m ? m[2] : '공연';
      const title = document.createElement('strong'); title.textContent = m ? m[3] : option.textContent;
      const time = document.createElement('span'); time.className = 'show-time'; time.textContent = m ? `${m[1]} 시작` : '공연 선택';
      button.append(venue, title, time);
      button.addEventListener('click', () => {
        $('event').value = option.value;
        $('event').dispatchEvent(new Event('change', {bubbles:true}));
        show('mode');
      });
      box.append(button);
    });
    if (!box.children.length) {
      box.textContent = '선택 가능한 공연 없음';
    }
  }
  new MutationObserver(() => { list(); summary(); }).observe($('event'), {childList:true});
  if ($('event').options.length) list();
  $('date').addEventListener('change', () => { if (step !== 'event') show('event'); });
  $('journeyBack').addEventListener('click', () => show(step === 'map' ? mapReturn : previous[step], true, -1));
  $('journeyChange').addEventListener('click', () => show('event', true, -1));
  $('journeyRestart').addEventListener('click', () => show('event', true, -1));
  // 버블 단계에서 처리하므로 기존 audience.js의 이동 방법 핸들러 뒤에 실행된다.
  $('mode').addEventListener('click', e => {
    const button = e.target.closest('button[data-v]');
    if (!button) return;
    show(button.dataset.v === 'car' ? 'topics' : 'transit');
  });
  document.querySelectorAll('[data-topic]').forEach(button => {
    button.addEventListener('click', () => {
      if (button.dataset.topic === 'map') mapReturn = step;
      show(button.dataset.topic);
    });
  });
  $('exitGate').addEventListener('park-zone-selected', () => {
    if (step === 'parking') show('direction');
  });
  $('egWay').addEventListener('park-direction-selected', () => {
    if (step === 'direction') show('guide');
  });
  $('skipDirection').addEventListener('click', () => show('guide'));
  show('event', false);
})();

"""
공연별 관객 차 대수(차량 이용현황, 7개 문 전체) × 대관 정산 인원(실제 관객 수).
  입력: data/raw/vhcle_use/KS_OLPARK_VHCLE_USE_STTUS_*.csv (문화 빅데이터 플랫폼 '올림픽공원 차량 이용현황', 주인 PC에 둠 — 용량이 커서 저장소에는 안 올림)
        data/raw/kspo_rent_info.csv (같은 플랫폼 '올림픽공원 대관 데이터', 2026-07판)
  파일 이름과 들어 있는 달이 다르고 같은 달이 두 파일에 있기도 하다 → 달마다 줄이 가장 많은 파일 하나만 쓴다.
  출력: data/processed/show_cars_vhcle.csv, data/processed/aud_cars.csv
  관객 차 = 시작 3시간 전~20분 뒤 입차, 2시간 넘게 머물고 시작 1.5~7시간 뒤 출차(모든 문). net = 같은 요일 유형(평일/주말·공휴일)·같은 시작 시각의
  큰 공연 없는 날 중앙값을 뺀 값. 회당 관객 = 대관 정산 인원 ÷ 그 대관 기간의 KSPO DOME 공연일 수.
"""
import glob, os
import sys; sys.path.insert(0,'scripts')
import pandas as pd, numpy as np
import inout_common as ic
best={}
for f in sorted(glob.glob('data/raw/vhcle_use/*VHCLE*.csv')):
    x=pd.read_csv(f,encoding='utf-8-sig'); x.columns=['dd','vid','tin','gin','tout','gout']
    for m,g in x.groupby(x.dd.str[:7]):
        if m not in best or len(g)>len(best[m]): best[m]=g
if not best: raise SystemExit('data/raw/vhcle_use/에 차량 이용현황 파일이 없습니다')
d=pd.concat([g.drop_duplicates() for g in best.values()],ignore_index=True).drop(columns='dd')
d['tin']=pd.to_datetime(d.tin,errors='coerce'); d['tout']=pd.to_datetime(d.tout,errors='coerce')
d['day']=d.tin.dt.normalize()
ev=pd.read_csv(ic.EVENTS,encoding='utf-8-sig')
big=set(pd.to_datetime(ev[ev['공연장'].isin(['KSPO DOME','핸드볼경기장','올림픽홀'])]['날짜']))
shows=[s for s in ic.kspo_shows('2024-03') if s[0]<'2026-01']
hol=set(pd.to_datetime(pd.read_csv("data/processed/holidays_kr.csv").iloc[:,0]))
we=lambda t: t.dayofweek>=5 or t.normalize() in hol
stay=(d.tout-d.tin).dt.total_seconds()/60
d['tod']=(d.tin-d.day).dt.total_seconds()/60
d['stay']=stay
base_days=[x for x in d.day.unique() if pd.Timestamp(x) not in big]
B=d[d.day.isin(base_days)]
rows=[]
B=B[(B.stay>=120)]
bday=pd.Series(pd.to_datetime(B.day.unique()))
isw={t:we(t) for t in bday}
B=B.assign(w=B.day.map(isw).astype(bool))
daysz=d.groupby('day').size()
okdays=set(daysz[daysz>=500].index)
cache={}
def basecnt(w,s0):
    if (w,s0) in cache: return cache[(w,s0)]
    y=B[(B.w==w)&(B.tod>=s0-180)&(B.tod<=s0+20)]
    om=(y.tout-y.day).dt.total_seconds()/60-s0
    y=y[(om>=90)&(om<=420)]
    c=y.groupby('day').size()
    alld=[t for t in bday if isw[t]==w and t in okdays]
    c=c.reindex(alld,fill_value=0)
    cache[(w,s0)]=(float(c.median()),len(c)); return cache[(w,s0)]
for date,st,title in shows:
    s=pd.Timestamp(f'{date} {st}'); s0=s.hour*60+s.minute
    x=d[d.day==s.normalize()]
    if len(x)<500: continue
    om=(x.tout-s).dt.total_seconds()/60
    a=x[(x.tod>=s0-180)&(x.tod<=s0+20)&(x.stay>=120)&(om>=90)&(om<=420)]
    bm,bn=basecnt(we(s),s0)
    rows.append(dict(date=date,start=st,title=title,cars=len(a),base=bm,nbase=bn,net=len(a)-bm,allin=len(x),
       gate_n2=(a.gin=='북2').mean(),gate_d2=(a.gin=='동2').mean(),gate_s2=(a.gin=='남2').mean(),
       other=(~a.gin.isin(['북2','동2','남2'])).mean()))
R=pd.DataFrame(rows); R.round(3).to_csv('data/processed/show_cars_vhcle.csv',index=False,encoding='utf-8-sig')
print(len(R)); print(R.describe().round(2).T[['mean','50%','min','max']])
# 대관 인원 매칭
r=pd.read_csv('data/raw/kspo_rent_info.csv',encoding='utf-8-sig')
r.columns=['place','hour','fac','abrv','kind','name','beg','end','days','req','act','plan','inout']
r=r[r.fac.str.contains('KSPO')&r.act.notna()&(r.act>0)].copy()
r['b']=pd.to_datetime(r.beg.astype(int).astype(str)); r['e']=pd.to_datetime(r.end.astype(int).astype(str))
kd=pd.to_datetime(ev[ev['공연장']=='KSPO DOME']['날짜']).drop_duplicates()
out=[]
for _,q in r.iterrows():
    sd=kd[(kd>=q.b)&(kd<=q.e)]
    if len(sd)==0: continue
    out.append(dict(name=q['name'],b=q.b,e=q.e,act=q.act,req=q.req,nshow=len(sd),per=q.act/len(sd),dates=[x.strftime('%Y-%m-%d') for x in sd]))
M=pd.DataFrame(out); print('대관-공연 매칭',len(M))
M2=[]
for _,m in M.iterrows():
    for dt in m.dates:
        z=R[R.date==dt]
        if len(z): M2.append(dict(date=dt,name=m['name'],per=m.per,act=m.act,nshow=m.nshow,cars=z.cars.iloc[0],net=z.net.iloc[0],start=z.start.iloc[0]))
M2=pd.DataFrame(M2).drop_duplicates('date'); M2.round(1).to_csv('data/processed/aud_cars.csv',index=False,encoding='utf-8-sig')
print('관객수 있는 공연일',len(M2)); print(M2[['per','cars','net']].describe().round(0))
print('corr per~net',round(M2[['per','net']].corr().iloc[0,1],3))
k=np.polyfit(M2.per,M2.net,1); print('net = %.4f*관객 + %.1f'%tuple(k))
print('관객 1천명당 차(중앙값)', round((M2.net/M2.per*1000).median(),1), '사분위', (M2.net/M2.per*1000).quantile([.25,.75]).round(1).tolist())
print(M2.sort_values('date').tail(12).to_string())

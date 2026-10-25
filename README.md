# 미국 증시 캘린더

S&P 500 · 나스닥 · 다우의 일별 종가와 등락률을 Apple 캘린더 스타일 월간 화면으로 보여줍니다.
GitHub Actions가 평일 아침 7시(한국 시간)에 전날 장 마감 결과를 자동으로 기록하고, GitHub Pages로 공개합니다.
API 키나 유료 서비스 없이 무료로 돌아갑니다.

## 구성

| 파일 | 역할 |
| --- | --- |
| `index.html` | 캘린더 화면 (상승 빨강, 하락 파랑) |
| `data/days.json` | 날짜별 기록 원본 |
| `data.js` | 화면이 읽는 데이터 (`update.py`가 생성) |
| `scripts/update.py` | Yahoo Finance에서 종가를 받아 기록 갱신 (표준 라이브러리만 사용) |
| `.github/workflows/update.yml` | 매일 자동 실행 + 커밋 |

## 판정 기준

- S&P 500 등락률 +0.1% 이상: **상승**, -0.1% 이하: **하락**, 그 사이: **보합**
- NYSE 휴장일은 **휴장**으로 표시 (`update.py`의 `HOLIDAYS`에 2026–2027년 등록)
- 매번 최근 45일을 다시 확인하므로, 실행이 빠진 날이 있어도 다음 실행 때 자동으로 채워집니다.

## 메모 추가

`data/days.json`에서 날짜에 `"summary": "..."`를 넣으면 오른쪽 상세 카드에 표시됩니다. 자동 갱신은 이 메모를 지우지 않습니다.
수정 후 `python3 scripts/update.py`를 실행하면 `data.js`도 함께 갱신됩니다.

## 직접 실행

```bash
python3 scripts/update.py
open index.html
```

수동 실행은 저장소의 **Actions → Update market data → Run workflow**에서도 할 수 있습니다.

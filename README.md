# HelpR&D (helprnd.com)

기업마당(bizinfo.go.kr)에 매일 올라오는 정부지원사업 공고를 모아 보여주는 홈페이지입니다.

## 구성
| 파일 | 하는 일 |
|---|---|
| `bizinfo_briefing.py` | 기업마당 공고 목록·상세(신청요건, 지원내용) 수집, 브리핑 PPT 만들기 |
| `build_site.py` | 새 공고를 모아 `site/data/announcements.json` 갱신, 그날 PPT를 `site/briefings/`에 저장 |
| `site/index.html` | 홈페이지 (지역·분야·검색·마감 필터, 신청요건·지원내용, 날짜별 PPT) |
| `data/state.json` | 마지막으로 가져온 공고 번호 (중복 없이 새 공고만 모으는 기록, 지우지 말 것) |
| `.github/workflows/daily.yml` | 매일 한국시간 오전 6:40에 위 작업을 실행하고 사이트에 올림 |

## 처음 한 번만 하는 설정

### 1. GitHub에 올리기
1. github.com에서 `helprnd.com`이라는 이름으로 **빈 저장소(Public)** 를 만든다. (README 추가하지 않기)
2. 이 폴더를 그 저장소에 올린다.

### 2. GitHub Pages 켜기
1. 저장소 → **Settings → Pages**
2. **Source**: `GitHub Actions` 선택
3. **Custom domain**: `helprnd.com` 입력 → Save
4. DNS 연결(아래 3번)이 끝나고 확인되면 **Enforce HTTPS** 체크

### 3. 호스팅케이알(hosting.kr) DNS 설정
호스팅케이알 로그인 → **나의 도메인(도메인 관리)** → `helprnd.com` → **DNS 관리(레코드 관리)** 에서 아래 레코드를 추가한다.
(기존에 `@`나 `www`에 걸린 A/CNAME 레코드나 '주차 페이지/포워딩'이 있으면 먼저 지운다)

| 타입 | 호스트(이름) | 값 |
|---|---|---|
| A | @ (비워둠) | 185.199.108.153 |
| A | @ (비워둠) | 185.199.109.153 |
| A | @ (비워둠) | 185.199.110.153 |
| A | @ (비워둠) | 185.199.111.153 |
| CNAME | www | juddmank.github.io. |

반영까지 보통 10분~몇 시간, 길면 하루 걸린다.

### 4. 첫 실행
저장소 → **Actions → 매일 공고 업데이트 → Run workflow** 를 누르면 바로 한 번 실행된다.
이후에는 매일 아침 자동으로 돈다.

## 손으로 돌려보기 (이 컴퓨터에서)
```
python build_site.py            # 새 공고 모으기 + 사이트 데이터 갱신
python -m http.server 8765 --directory site   # http://localhost:8765 에서 확인
```

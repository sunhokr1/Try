# 🛒 쇼핑 리스트

아이템을 추가·수정·삭제·체크할 수 있는 간단한 Streamlit 쇼핑 리스트 앱입니다. 자세한 요구사항은 [PRD.md](PRD.md)를 참고하세요.

## 설치

```bash
pip install -r requirements.txt
```

## 실행

```bash
python -m streamlit run app.py
```

브라우저에서 http://localhost:8501 로 접속합니다.

## 데이터 저장

아이템은 `data/shopping_list.json`에 저장됩니다. Streamlit Community Cloud에서는 앱이 재시작되면 이 파일이 초기화될 수 있습니다.

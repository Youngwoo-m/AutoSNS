"""Deploy the static website together with the Netlify functions.

예전에는 사이트 파일만 zip 으로 올렸는데, zip 배포에는 함수가 빠져 Netlify 가 기존 함수
(학식 hak · 기상특보 wthr · 재난 소식 alerts · 길찾기 kroute · 버스 도착 busarr)를 지웠다
(2026-10-18 문제 목록 배포 뒤 저녁 룰렛·셔틀 앱 기능 중단). 그래서 함수까지 함께 올리는
deploy_full 로 넘긴다. 자격 증명·대기열은 여전히 사이트에 들어가지 않는다.
"""
from deploy_full import deploy

if __name__ == '__main__':
    deploy()

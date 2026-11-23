import type { ViewMode } from "../lib/store";

/** 해부 투어: 단계마다 보기 모드, 분해 정도, 카메라가 향할 부품, 켤 층을 정한다. 설명 글은 부품 도감(서버)에서 가져온다. */
export interface TourStep { title: string; part: string; infoId: string; view: ViewMode; explode: number; focus: string | null; flux?: boolean; coolant?: boolean; pose?: [number[], number[]]; blurb: string }
export const TOUR: TourStep[] = [
  { title: "1 · 외관", part: "전체", infoId: "housing", view: "assembled", explode: 0, focus: null, pose: [[8.5, 3.4, 9.5], [0.2, 0, 0]], blurb: "2004년형 Toyota Prius의 구동모터(MG2)입니다. 지름 29.9 cm, 길이 20.5 cm의 케이스 안에 고정자와 회전자가 들어 있습니다." },
  { title: "2 · 하우징과 냉각", part: "하우징", infoId: "housing", view: "assembled", explode: 0, focus: "housing", coolant: true, blurb: "케이스 벽 안의 워터재킷으로 냉각수가 흐르며 열을 가져갑니다. 푸른 입자가 냉각수 흐름의 도식입니다." },
  { title: "3 · 하우징을 벗긴다", part: "하우징", infoId: "housing", view: "exploded", explode: 0.5, focus: "stator_core", pose: [[3.5, 3.2, 14.5], [0.2, 0.3, 0]], blurb: "하우징과 단자부, 앞뒤 덮개가 축을 따라 빠져나갑니다. 속에 고정자가 있습니다." },
  { title: "4 · 고정자와 3상 권선", part: "고정자 권선", infoId: "windings", view: "exploded", explode: 0.62, focus: "windings", blurb: "48개 슬롯에 3상 구리 코일이 들어 있습니다. 빨강·노랑·파랑이 A·B·C 상이고, 코일 머리(엔드턴)는 슬롯 6칸을 건너뜁니다." },
  { title: "5 · 회전자를 뽑는다", part: "회전자 철심", infoId: "rotor_core", view: "exploded", explode: 0.85, focus: "rotor_core", blurb: "회전자가 축을 따라 빠져나옵니다. 철심에 V자 자석 구멍이 보입니다." },
  { title: "6 · 영구자석 16개", part: "영구자석", infoId: "magnets", view: "exploded", explode: 1, focus: "magnets", blurb: "회전자에서 꺼낸 네오디뮴 자석입니다. 붉은색은 N극, 푸른색은 S극 쪽 자석이고 한 극에 두 장이 V자로 놓입니다." },
  { title: "7 · 단면과 자속 분포", part: "횡단면", infoId: "stator_core", view: "section", explode: 0, focus: null, flux: true, pose: [[9.2, 0.6, 1.2], [0, 0, 0]], blurb: "모터를 가운데에서 자른 단면입니다. 흰 선은 이 프로젝트가 FEA로 푼 자속선이고, 바탕색은 자속밀도입니다." },
];

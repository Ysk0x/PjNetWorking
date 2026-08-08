"""
rules.py
--------
ฟังก์ชันคำนวณแต้มและตัดสินผลของเกมป๊อกเด้ง
เขียนเป็น pure function ล้วนๆ (รับไพ่เข้ามา คืนผลลัพธ์กลับไป) ไม่แตะ Player/Room/network
เพื่อให้ทดสอบได้ตรงๆ โดยไม่ต้องรัน server เลย

โครงสร้างผลลัพธ์ (dict) ออกแบบให้มี field เผื่อขยายสำหรับ phase 2
เช่น "multiplier" ไว้รองรับเด้ง/ไพ่พิเศษ 3 ใบในอนาคต โดยไม่ต้องแก้ signature ฟังก์ชัน
"""


def calculate_score(cards):
    """
    รวมแต้มไพ่ทั้งหมดแล้ว mod 10 (เอาแค่หลักหน่วย)
    cards: list ของ Card
    """
    total = sum(card.point for card in cards)
    return total % 10


def is_pok(cards):
    """
    เช็คว่าไพ่ 2 ใบแรกเป็น "ป๊อก" หรือไม่ (รวมแต้มได้ 8 หรือ 9)
    คืนค่า (True/False, แต้ม) เช่น (True, 9) หรือ (False, 5)
    ป๊อกเช็คได้แค่ตอนมีไพ่ 2 ใบเท่านั้น (ยังไม่จั่วใบที่ 3)
    """
    if len(cards) != 2:
        return False, calculate_score(cards)
    score = calculate_score(cards)
    return score in (8, 9), score


def get_hand_result(cards):
    """
    สรุปผลของไพ่ในมือ 1 คน (ใช้ทั้งตอนเช็คป๊อกและตอนเปิดไพ่ตอนจบ)
    คืน dict ที่ขยาย field เพิ่มได้ในอนาคต เช่น "multiplier" สำหรับเด้ง/ตอง/เรียง
    """
    score = calculate_score(cards)
    pok, _ = is_pok(cards) if len(cards) == 2 else (False, score)
    return {
        "score": score,
        "is_pok": pok,
        "multiplier": 1,  # เผื่อ phase 2: เด้ง/ตอง/สเตรทฟลัช ฯลฯ จะปรับค่านี้
    }


def compare(dealer_cards, player_cards):
    """
    ตัดสินแพ้ชนะระหว่างเจ้ามือกับผู้เล่น 1 คน
    กติกา: ใครแต้มมากกว่าชนะ (ป๊อก 9 > ป๊อก 8 > แต้มธรรมดา ที่แต้มเท่ากันถือว่าเจ้ามือชนะ - ตามธรรมเนียมป๊อกเด้งทั่วไป)
    คืน dict บอกผู้ชนะและรายละเอียดแต้มของทั้งสองฝ่าย
    """
    dealer_result = get_hand_result(dealer_cards)
    player_result = get_hand_result(player_cards)

    dealer_rank = _rank_value(dealer_result)
    player_rank = _rank_value(player_result)

    if player_rank > dealer_rank:
        winner = "player"
    else:
        # แต้มเท่ากันถือว่าเจ้ามือชนะ (เจ้ามือได้เปรียบ ตามธรรมเนียมเกมไพ่ไทย)
        winner = "dealer"

    return {
        "winner": winner,
        "dealer": dealer_result,
        "player": player_result,
    }


def _rank_value(hand_result):
    """
    แปลงผลลัพธ์ไพ่เป็นตัวเลขเดียวสำหรับเทียบกัน
    ป๊อก 9 > ป๊อก 8 > แต้มธรรมดา (0-7)
    """
    if hand_result["is_pok"]:
        # ป๊อก 9 ได้ 109, ป๊อก 8 ได้ 108 (บวก 100 เพื่อให้สูงกว่าแต้มธรรมดาเสมอ)
        return 100 + hand_result["score"]
    return hand_result["score"]

from copy import deepcopy
from decimal import Decimal
import unittest
from game_state import GameState, MAX_ENERGY, MAX_CLICKS
from systems.upgrades import UPGRADES, MAX_LEVEL
from ui.formatting import format_en

class EconomyTests(unittest.TestCase):
    def test_initial_state_and_click(self):
        s = GameState()
        self.assertEqual(s.click_power, 1)
        self.assertEqual(s.auto_rate, 0)
        self.assertEqual(s.click().amount, 1)
        self.assertEqual((s.energy, s.total_earned, s.clicks), (1, 1, 1))

    def test_purchase_deducts_cost_not_total(self):
        s = GameState(Decimal(25), Decimal(25))
        self.assertTrue(s.buy('pulse').success)
        self.assertEqual((s.energy, s.total_earned, s.levels['pulse'], s.click_power), (0, 25, 1, 2))
        self.assertEqual(s.click().amount, 2)

    def test_prices_and_growth(self):
        self.assertEqual([UPGRADES['pulse'].cost(i) for i in range(4)], [25, 37, 53, 77])
        self.assertEqual([UPGRADES['reactor'].cost(i) for i in range(3)], [80, 124, 193])
        for u in UPGRADES.values():
            prices = [u.cost(i) for i in range(MAX_LEVEL)]
            self.assertTrue(all(b > a for a, b in zip(prices, prices[1:])))

    def test_rejection_is_transactional(self):
        s = GameState()
        for key in ('pulse', 'reactor', 'unknown'):
            before = s.to_dict()
            self.assertFalse(s.buy(key).success)
            self.assertEqual(s.to_dict(), before)

    def test_unlock_is_lifetime_based(self):
        s = GameState(Decimal(0), Decimal(50))
        self.assertTrue(s.unlocked('reactor'))
        s.total_earned = Decimal(49)
        self.assertFalse(s.unlocked('reactor'))

    def test_exact_affordability_and_fractional_auto(self):
        s = GameState(Decimal('79.99'), Decimal(100), levels={'pulse': 0, 'reactor': 0})
        self.assertFalse(s.buy('reactor').success)
        s.energy = Decimal(80)
        self.assertTrue(s.buy('reactor').success)
        self.assertEqual(s.advance(.125), Decimal('.250'))
        self.assertEqual(s.auto_rate, 2)

    def test_tick_partition_invariance(self):
        a, b = GameState(), GameState()
        a.levels['reactor'] = b.levels['reactor'] = 3
        a.advance(10)
        for _ in range(100):
            b.advance(.1)
        self.assertEqual(a.energy, b.energy)
        self.assertEqual(a.total_earned, 60)

    def test_invalid_delta_rejected(self):
        for value in (-1, float('nan'), float('inf'), True, '1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                GameState().advance(value)

    def test_level_cap(self):
        s = GameState(MAX_ENERGY, MAX_ENERGY, levels={'pulse': MAX_LEVEL, 'reactor': MAX_LEVEL})
        before = s.to_dict()
        self.assertFalse(s.buy('pulse').success)
        self.assertEqual(s.to_dict(), before)
        with self.assertRaises(ValueError):
            UPGRADES['pulse'].cost(MAX_LEVEL)

    def test_resource_cap_no_overflow(self):
        s = GameState(MAX_ENERGY - 1, MAX_ENERGY - 1, levels={'pulse': 2, 'reactor': 1})
        self.assertEqual(s.click().amount, 1)
        self.assertEqual(s.energy, MAX_ENERGY)
        self.assertEqual(s.advance(100), 0)
        self.assertFalse(s.click().success)

    def test_click_count_cap(self):
        s = GameState(clicks=MAX_CLICKS)
        self.assertFalse(s.click().success)
        self.assertEqual(s.energy, 0)

    def test_distinct_level_dictionaries(self):
        a, b = GameState(), GameState()
        a.levels['pulse'] = 10
        self.assertEqual(b.levels['pulse'], 0)

    def test_early_progression_is_playable(self):
        s = GameState()
        for _ in range(25):
            s.click()
        self.assertTrue(s.buy('pulse').success)
        for _ in range(40):
            s.click()
        self.assertTrue(s.buy('reactor').success)
        self.assertEqual(s.auto_rate, 2)
        self.assertEqual(s.total_earned, 105)
        s.advance(5)
        self.assertEqual(s.energy, 10)

    def test_display_never_rounds_price_down_in_model(self):
        self.assertEqual(format_en(Decimal('1234.56')), '1.23 K')
        self.assertEqual(format_en(Decimal(0)), '0')
        self.assertEqual(format_en(Decimal('999.999')), '999.99')
        self.assertEqual(format_en(MAX_ENERGY), '1.00E+60')

class ValidationTests(unittest.TestCase):
    def test_roundtrip(self):
        s = GameState(Decimal('135.125'), Decimal('900.125'), 100,
                      {'pulse': 3, 'reactor': 2})
        s.settings.reduced_motion = True
        self.assertEqual(GameState.from_dict(s.to_dict()).to_dict(), s.to_dict())

    def test_corrupt_numbers(self):
        for value in ('NaN', 'Infinity', '-1', '1e61', '1e-9999', '0e99999', True, 5, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                data = GameState().to_dict()
                data['energy'] = value
                GameState.from_dict(data)

    def test_corrupt_structure(self):
        base = GameState().to_dict()
        cases = [None, [], {'version': 2}]
        for changes in ({'version': True}, {'levels': {'pulse': -1, 'reactor': 0}},
                        {'levels': {'pulse': True, 'reactor': 0}}, {'levels': {}},
                        {'clicks': -1}, {'clicks': True}, {'settings': {}},
                        {'settings': {'reduced_motion': 'false'}}, {'energy': '1'},
                        {'click_power': '50'}, {'auto_rate': '1'}):
            data = deepcopy(base)
            data.update(changes)
            cases.append(data)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                GameState.from_dict(data)

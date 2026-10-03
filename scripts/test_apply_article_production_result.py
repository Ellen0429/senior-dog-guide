import unittest

from scripts.apply_article_production_result import ApplyError, apply_pending_replacement, PENDING_PAIR


def _block(n: int) -> str:
    return (
        f'<a href="/go?{PENDING_PAIR}&amp;placement=image">img{n}</a>\n'
        f'<a href="/go?{PENDING_PAIR}&amp;placement=product_name">name{n}</a>\n'
        f'<a href="/go?{PENDING_PAIR}&amp;placement=cta">cta{n}</a>\n'
    )


class TestApplyPendingReplacement(unittest.TestCase):
    def test_replaces_three_products_in_order(self):
        html = _block(1) + _block(2) + _block(3)
        result = apply_pending_replacement(html, content_id=35, product_ids=[75, 76, 77])
        self.assertNotIn("PENDING", result)
        self.assertIn('content_id=35&amp;product_id=75&amp;placement=image', result)
        self.assertIn('content_id=35&amp;product_id=75&amp;placement=product_name', result)
        self.assertIn('content_id=35&amp;product_id=75&amp;placement=cta', result)
        self.assertIn('content_id=35&amp;product_id=76&amp;placement=image', result)
        self.assertIn('content_id=35&amp;product_id=77&amp;placement=cta', result)
        # order preserved: product 75's block appears before 76's
        self.assertLess(result.index("product_id=75"), result.index("product_id=76"))
        self.assertLess(result.index("product_id=76"), result.index("product_id=77"))

    def test_single_product_article(self):
        html = _block(1)
        result = apply_pending_replacement(html, content_id=13, product_ids=[24])
        self.assertNotIn("PENDING", result)
        self.assertEqual(result.count("product_id=24"), 3)

    def test_mismatched_count_raises_without_modifying_semantics(self):
        html = _block(1) + _block(2)  # 6 PENDING pairs
        with self.assertRaises(ApplyError):
            apply_pending_replacement(html, content_id=1, product_ids=[1, 2, 3])

    def test_non_multiple_of_three_raises(self):
        html = f'<a href="/go?{PENDING_PAIR}&amp;placement=image">x</a>'  # 1 PENDING pair only
        with self.assertRaises(ApplyError):
            apply_pending_replacement(html, content_id=1, product_ids=[1])

    def test_unrelated_text_outside_pending_pairs_is_untouched(self):
        html = "<p>日本語のテキスト</p>" + _block(1) + "<p>末尾のテキスト</p>"
        result = apply_pending_replacement(html, content_id=5, product_ids=[9])
        self.assertIn("日本語のテキスト", result)
        self.assertIn("末尾のテキスト", result)


if __name__ == "__main__":
    unittest.main()

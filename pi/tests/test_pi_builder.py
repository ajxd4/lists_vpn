import importlib.util
import pathlib
import unittest
from unittest.mock import patch

BASE = pathlib.Path(__file__).resolve().parent.parent


def load(filename):
    spec = importlib.util.spec_from_file_location(filename.replace('-', '_'), BASE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


convert = load('convert-unifi.py')
feeds = load('refresh-sources.py')
coverage = load('verify-proton-coverage.py')


class ConversionTests(unittest.TestCase):
    def test_mixed_ip_ranges_and_host_format(self):
        self.assertEqual(convert.convert(['2.26.8.0/22', '5.157.13.3/32', '2.58.241.67', '#comment']),
                         ['2.26.8.0/22', '5.157.13.3', '2.58.241.67'])

    def test_reject_invalid_and_noncanonical(self):
        with self.assertRaises(ValueError):
            convert.convert(['203.0.113.42/24'])
        with self.assertRaises(ValueError):
            convert.convert(['0.0.0.0/999'])
        with self.assertRaises(ValueError):
            convert.convert([])

    def test_address_coverage_unchanged(self):
        import ipaddress
        src = ['2.26.8.0/22', '5.157.13.3/32', '2.58.241.67/32', '1.2.3.0/24']
        dst = convert.convert(src)
        self.assertEqual([ipaddress.IPv4Network(x).num_addresses for x in src],
                         [ipaddress.IPv4Network(x).num_addresses for x in dst])
        self.assertEqual([ipaddress.IPv4Network(x) for x in src],
                         [ipaddress.IPv4Network(x) for x in dst])


class ProtonCoverageTests(unittest.TestCase):
    def test_included_by_cidr_and_host(self):
        missing, count = coverage.uncovered(['1.1.1.1', '8.8.8.8'], ['1.1.1.0/24', '8.8.8.8/32'])
        self.assertEqual((missing, count), ([], 2))

    def test_overlapping_ranges(self):
        missing, count = coverage.uncovered(['1.1.1.250'], ['1.1.1.0/24', '1.1.1.128/25', '1.1.1.200/32'])
        self.assertEqual((missing, count), ([], 1))

    def test_uncovered_ip_is_detected(self):
        missing, count = coverage.uncovered(['1.1.1.1', '9.9.9.9'], ['1.1.1.0/24', '8.8.8.0/24'])
        self.assertEqual((missing, count), (['9.9.9.9'], 2))


class SourceTests(unittest.TestCase):
    def test_mullvad(self):
        with patch.object(feeds, 'download', return_value='[{"ipv4_addr_in":"1.1.1.1"},{"ipv4_addr_in":"9.9.9.9"}]'):
            self.assertEqual(feeds.mullvad(), ['1.1.1.1','9.9.9.9'])

    def test_pia_signed_json_first_line(self):
        fixture = '{"regions":[{"servers":{"wg":[{"ip":"1.1.1.1"}],"meta":[{"ip":"8.8.8.8"}]}}]}\nSIGNATURE\n'
        with patch.object(feeds, 'download', return_value=fixture):
            self.assertCountEqual(feeds.pia(), ['1.1.1.1','8.8.8.8'])

    def test_apple_csv(self):
        with patch.object(feeds, 'download', return_value='17.0.0.0/16,US,US-CA\n2600:abcd::/48,US,US-CA\n'):
            self.assertEqual(feeds.apple(), ['17.0.0.0/16'])

    def test_proton_comments_and_deduplication(self):
        example = '# ProtonVPN IPs\n\n1.1.1.1\n9.9.9.9 # inline note\n1.1.1.1\n'
        with patch.object(feeds, 'download', return_value=example):
            self.assertEqual(feeds.normalize('protonvpn.txt', feeds.proton(), 2, 100),
                             ['1.1.1.1', '9.9.9.9'])

    def test_proton_invalid_data_fails_closed(self):
        for text in ('# header only\n', '1.1.1.1\nnot-an-ip\n', '10.0.0.1\n', '2001:db8::1\n'):
            with self.subTest(text=text), patch.object(feeds, 'download', return_value=text):
                if 'header only' in text:
                    with self.assertRaises(ValueError):
                        feeds.normalize('protonvpn.txt', feeds.proton(), 1, 100)
                else:
                    with self.assertRaises(ValueError):
                        feeds.proton()

    def test_normalize_rejects_private_and_small(self):
        with self.assertRaises(ValueError):
            feeds.normalize('test', ['10.0.0.1','192.168.1.1'], 1, 10)
        self.assertEqual(feeds.normalize('test', ['1.1.1.1','1.1.1.1','8.8.8.8'], 2, 10),
                         ['1.1.1.1', '8.8.8.8'])


if __name__ == '__main__':
    unittest.main()

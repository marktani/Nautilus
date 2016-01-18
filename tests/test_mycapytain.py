from nautilus.mycapytain import NautilusEndpoint, MY_CAPYTAIN, XML

from MyCapytain.resources.inventory import TextInventory
from MyCapytain.resources.texts.api import Passage
from MyCapytain.common.utils import xmlparser
from unittest import TestCase


class ResponseTest(TestCase):

    def setUp(self):
        self.endpoint = NautilusEndpoint(["./tests/test_data/farsiLit"])

    def test_with_get_capabilities(self):
        response = self.endpoint.getCapabilities(category="translation", format=MY_CAPYTAIN)
        ti = TextInventory(resource=response)
        self.assertEqual(
            len(ti["urn:cts:farsiLit:hafez.divan"].texts), 2,
            "Asserts that only two texts has been added to the TI"
        )

    def test_with_get_capabilities_cts_response(self):
        response = self.endpoint.getCapabilities(category="translation", format=XML)
        self.assertIn(
            "<requestFilters>category=translation</requestFilters>", response,
            "Filters should be listed"
        )
        ti = TextInventory(resource=response)
        self.assertEqual(
            len(ti["urn:cts:farsiLit:hafez.divan"].texts), 2,
            "Asserts that only two texts has been added to the TI"
        )

    def test_get_passage_complete_urn(self):
        """ Test Get Passage """
        response, metadata = self.endpoint.getPassage("urn:cts:farsiLit:hafez.divan.perseus-eng1:1.1.1.1", format=MY_CAPYTAIN)
        self.assertEqual(
            response.text(),
            "Ho ! Saki, pass around and offer the bowl (of love for God) : ### ",
            "It should be possible to retrieve text"
        )

    def test_get_passage_partial_urn(self):
        """ Test Get Passage """
        response, metadata = self.endpoint.getPassage("urn:cts:farsiLit:hafez.divan:1.1.1.1", format=MY_CAPYTAIN)
        self.assertEqual(
            response.text(),
            "الا یا ایها الساقی ادر کاسا و ناولها ### ",
            "It should be possible to retrieve text from edition without veersion"
        )

    def test_get_passage_formatted(self):
        response = self.endpoint.getPassage("urn:cts:farsiLit:hafez.divan:1.1.1.1", format=XML)
        self.assertEqual(
            Passage(resource=xmlparser(response), urn="urn:cts:farsiLit:hafez.divan:1.1.1.1").text().strip(),
            "الا یا ایها الساقی ادر کاسا و ناولها ###",
            "API Response should be parsable by MyCapytain Library"
        )

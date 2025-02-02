import json
import re
from abc import abstractmethod

from MyCapytain.common.constants import Mimetypes, XPATH_NAMESPACES
from MyCapytain.common.reference import CtsReference
from MyCapytain.common.utils.xml import xmlparser
from MyCapytain.resolvers.cts.api import HttpCtsResolver
from MyCapytain.resources.collections.cts import XmlCtsTextInventoryMetadata as TextInventory, \
    XmlCtsCitation as Citation
from MyCapytain.resources.texts.remote.cts import CtsText as Text
from MyCapytain.retrievers.cts5 import HttpCtsRetriever
from flask import Flask
from logassert import logassert
from lxml.etree import tostring
from pyld.jsonld import expand

from .mockups.dts import (
    coll as dts_coll_mockups,
    refs as dts_refs_mockups
)
from .util import normalize_uri_key

from capitains_nautilus.flask_ext import FlaskNautilus
import logging
import link_header
import urltools.urltools as urltools



logging.basicConfig(level=logging.CRITICAL)
logger = logging.getLogger("some_logger")


class SetupModule:
    @abstractmethod
    def generate_resolver(self, directories):
        raise NotImplementedError()

    def setUp(self):
        # Clean up noise...

        app = Flask("Nautilus")
        self.nautilus_resolver = self.generate_resolver(["./tests/test_data/latinLit"])
        self.nautilus = FlaskNautilus(
            app=app,
            resolver=self.nautilus_resolver,
            logger=logger
        )
        self.cache = None
        self.app = app.test_client()
        self.parent = HttpCtsRetriever("/cts")
        self.resolver = HttpCtsResolver(endpoint=self.parent)
        logassert.setup(self, self.nautilus.logger.name)
        self.nautilus.logger.disabled = True

        def call(this, parameters={}):
            """ Call an endpoint given the parameters

            :param parameters: Dictionary of parameters
            :type parameters: dict
            :rtype: text
            """

            parameters = {
                key: str(parameters[key]) for key in parameters if parameters[key] is not None
            }
            if this.inventory is not None and "inv" not in parameters:
                parameters["inv"] = this.inventory

            request = self.app.get("/cts?{}".format(
                "&".join(
                    ["{}={}".format(key, value) for key, value in parameters.items()])
                )
            )
            self.parent.called.append(parameters)
            return request.data.decode()

        self.parent.called = []
        self.parent.call = lambda x: call(self.parent, x)


class CTSModule:
    def test_cors(self):
        """ Check that CORS enabling works """
        self.assertEqual(self.app.get("/cts?request=GetCapabilities").headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(self.app.get("/cts?request=GetCapabilities").headers["Access-Control-Allow-Methods"], "OPTIONS, GET")

    def test_restricted_cors(self):
        """ Check that area-restricted cors works """
        app = Flask("Nautilus")
        FlaskNautilus(
            app=app,
            resolver=self.generate_resolver(["./tests/test_data/latinLit"]),
            access_Control_Allow_Methods={"r_cts": "OPTIONS", "r_dts_collection": "OPTIONS",
                                          "r_dts_collections": "OPTIONS"},
            access_Control_Allow_Origin={"r_cts": "foo.bar", "r_dts_collection": "*",
                                         "r_dts_collections": "*"}
        )
        _app = app.test_client()
        self.assertEqual(_app.get("/cts?request=GetCapabilities").headers["Access-Control-Allow-Origin"], "foo.bar")
        self.assertEqual(_app.get("/cts?request=GetCapabilities").headers["Access-Control-Allow-Methods"], "OPTIONS")

    def test_get_capabilities(self):
        """ Check the GetCapabilities request """
        response = self.app.get("/cts?request=GetCapabilities")
        a = TextInventory.parse(resource=response.data.decode())
        self.assertEqual(
            str(a["urn:cts:latinLit:phi1294.phi002.perseus-lat2"].urn), "urn:cts:latinLit:phi1294.phi002.perseus-lat2",
        )
        # Test for cache : only works in Cache situation, with specific SIMPLE BACKEND
        if self.cache is not None:
            self.assertGreater(
                len(self.cache.cache._cache), 0,
                "There should be something cached"
            )

    def test_partial_capabilities(self):
        response = self.resolver.getMetadata(objectId="urn:cts:latinLit:phi1294.phi002.perseus-lat2")
        self.assertEqual(
            response.id, "urn:cts:latinLit:phi1294.phi002.perseus-lat2"
        )
        if self.cache is not None:
            self.assertGreater(
                len(self.cache.cache._cache), 0,
                "There should be something cached"
            )

    def test_get_passage(self):
        """ Check the GetPassage request """
        passage = self.resolver.getTextualNode("urn:cts:latinLit:phi1294.phi002.perseus-lat2", "1.pr.1")
        self.assertEqual(
            passage.export(Mimetypes.PLAINTEXT), "Spero me secutum in libellis meis tale temperamen-"
        )
        self.assertCountEqual(
            self.parent.called, [{"request": "GetPassage", "urn": "urn:cts:latinLit:phi1294.phi002.perseus-lat2:1.pr.1"}]
        )
        p, n = passage.siblingsId
        self.assertEqual((None, "1.pr.2"), (p, n), "Passage range should be given")
        self.assertCountEqual(
            self.parent.called,
            [
                {"request": "GetPassage", "urn": "urn:cts:latinLit:phi1294.phi002.perseus-lat2:1.pr.1"},
                {"request": "GetPrevNextUrn", "urn": "urn:cts:latinLit:phi1294.phi002.perseus-lat2:1.pr.1"}
            ]
        )
        if self.cache is not None:
            self.assertGreater(
                len(self.cache.cache._cache), 0,
                "There should be something cached"
            )

    def test_get_valid_reff(self):
        passages = self.resolver.getReffs("urn:cts:latinLit:phi1294.phi002.perseus-lat2", subreference="1.pr")
        self.assertEqual(
            passages, [
                "1.pr.1", '1.pr.2', '1.pr.3', '1.pr.4', '1.pr.5', '1.pr.6', '1.pr.7', '1.pr.8', '1.pr.9', '1.pr.10',
                '1.pr.11', '1.pr.12', '1.pr.13', '1.pr.14', '1.pr.15', '1.pr.16', '1.pr.17', '1.pr.18', '1.pr.19',
                '1.pr.20', '1.pr.21', '1.pr.22'
            ]
        )
        self.assertCountEqual(
            self.parent.called, [{
                "request": "GetValidReff", "urn": "urn:cts:latinLit:phi1294.phi002.perseus-lat2:1.pr", "level":"1"
            }]
        )
        passages = self.resolver.getReffs(
            "urn:cts:latinLit:phi1294.phi002.perseus-lat2",
            subreference="1.pr.1-1.pr.5",
            level=0
        )
        self.assertEqual(
            passages, [
                "1.pr.1", '1.pr.2', '1.pr.3', '1.pr.4', '1.pr.5'
            ]
        )
        self.assertCountEqual(
            self.parent.called, [{
                "request": "GetValidReff",
                "urn": "urn:cts:latinLit:phi1294.phi002.perseus-lat2:1.pr",
                "level": "1"
            }, {
                "request": "GetValidReff",
                "urn": "urn:cts:latinLit:phi1294.phi002.perseus-lat2:1.pr.1-1.pr.5",
                "level": "0"
            }]
        )
        if self.cache is not None:
            self.assertGreater(
                len(self.cache.cache._cache), 0,
                "There should be something cached"
            )

    def test_get_passage_plus(self):
        """ Check the GetPassagePlus request """
        response = self.resolver.getTextualNode(
            "urn:cts:latinLit:phi1294.phi002.perseus-lat2", "1.pr.1",
            prevnext=True, metadata=True
        )
        self.assertEqual(
            response.export(Mimetypes.PLAINTEXT), "Spero me secutum in libellis meis tale temperamen-"
        )
        self.assertEqual(
            response.prev, None
        )
        self.assertEqual(
            str(response.next.reference), "1.pr.2"
        )

        response = self.resolver.getTextualNode(
            "urn:cts:latinLit:phi1294.phi002.perseus-lat2", "1.pr.10",
            prevnext=True, metadata=True
        )
        self.assertEqual(
            response.export(Mimetypes.PLAINTEXT), "borum veritatem, id est epigrammaton linguam, excu-",
            "Check Range works on normal middle GetPassage"
        )
        self.assertEqual(
            str(response.prev.reference), "1.pr.9"
        )
        self.assertEqual(
            str(response.next.reference), "1.pr.11"
        )

        response = self.resolver.getTextualNode(
            "urn:cts:latinLit:phi1294.phi002.perseus-lat2", "1.pr.10-1.pr.11",
            prevnext=True, metadata=True
        )
        self.assertEqual(
            response.export(Mimetypes.PLAINTEXT), "borum veritatem, id est epigrammaton linguam, excu- "
                             "sarem, si meum esset exemplum: sic scribit Catullus, sic ",
            "Check Range works on GetPassagePlus"
        )
        self.assertEqual(
            str(response.prev.reference), "1.pr.8-1.pr.9",
            "Check Range works on GetPassagePlus and compute right prev"
        )
        self.assertEqual(
            str(response.next.reference), "1.pr.12-1.pr.13",
            "Check Range works on GetPassagePlus and compute right next"
        )
        if self.cache is not None:
            self.assertGreater(
                len(self.cache.cache._cache), 0,
                "There should be something cached"
            )

    def test_get_prevnext_urn(self):
        """ Check the GetPrevNext request """
        text = Text(urn="urn:cts:latinLit:phi1294.phi002.perseus-lat2", retriever=self.parent)
        p, n = text.getPrevNextUrn(CtsReference("1.pr.1"))
        self.assertEqual(
            p, None
        )
        self.assertEqual(
            n, "1.pr.2"
        )

        response = text.getPassagePlus(CtsReference("1.pr.10"))
        self.assertEqual(
            str(response.prev.reference), "1.pr.9",
            "Check Range works on normal middle GetPassage"
        )
        self.assertEqual(
            str(response.next.reference), "1.pr.11"
        )

        response = text.getPassagePlus(CtsReference("1.pr.10-1.pr.11"))
        self.assertEqual(
            str(response.prev.reference), "1.pr.8-1.pr.9",
            "Check Range works on GetPassagePlus and compute right prev"
        )
        self.assertEqual(
            str(response.next.reference), "1.pr.12-1.pr.13",
            "Check Range works on GetPassagePlus and compute right next"
        )
        if self.cache is not None:
            self.assertGreater(
                len(self.cache.cache._cache), 0,
                "There should be something cached"
            )

    def test_get_label(self):
        """Check get Label"""
        # Need to parse with Citation and parse individually or simply check for some equality
        data = self.app.get("/cts?request=GetLabel&urn=urn:cts:latinLit:phi1294.phi002.perseus-lat2")\
            .data.decode("utf-8").replace("\n", "")
        parsed = xmlparser(data)
        label = parsed.xpath(".//ti:label", namespaces=XPATH_NAMESPACES)
        label_str = re.sub("\s+", " ", tostring(label[0], encoding=str)).replace("\n", "")
        self.assertIn(
            '<groupname xml:lang="eng">Martial</groupname>',
            label_str,
            "groupname should be exported correctly"
        )
        self.assertIn(
            '<title xml:lang="eng">Epigrammata</title>',
            label_str,
            "title should be exported correctly"
        )
        self.assertIn(
            '<description xml:lang="eng"> M. Valerii Martialis Epigrammaton libri / recognovit W. Heraeus </description>',
            label_str,
            "description should be exported correctly"
        )
        self.assertIn(
            '<label xml:lang="eng">Epigrammata</label>',
            label_str,
            "label should be exported correctly"
        )
        citation = Citation.ingest(label[0])
        self.assertEqual(
            len(citation), 3, "There should be three level of citation"
        )
        self.assertEqual(
            citation.name, "book", "First level is book"
        )
        if self.cache is not None:
            self.assertGreater(
                len(self.cache.cache._cache), 0,
                "There should be something cached"
            )

    def test_missing_request(self):
        """Check get Label"""
        # Need to parse with Citation and parse individually or simply check for some equality
        data = self.app.get("/cts").data.decode("utf-8").replace("\n", "")
        self.assertIn(
            "Request missing one or more required parameters", data, "Error message should be displayed"
        )
        self.assertIn(
            "MissingParameter", data, "Error name should be displayed"
        )

    def test_InvalidUrn_request(self):
        """Check get Label"""
        # Need to parse with Citation and parse individually or simply check for some equality
        data = self.app.get("/cts?request=GetPassage&urn=urn:cts:latinLit:phi1295").data.decode()
        self.assertIn(
            "Syntactically valid URN refers to an invalid level of collection for this request", data, "Error message should be displayed"
        )
        self.assertIn(
            "InvalidURN", data, "Error name should be displayed"
        )
        data = self.app.get("/cts?request=GetPassagePlus&urn=urn:cts:latinLit:phi1294").data.decode()
        self.assertIn(
            "Syntactically valid URN refers to an invalid level of collection for this request", data, "Error message should be displayed"
        )
        self.assertIn(
            "InvalidURN", data, "Error name should be displayed"
        )

    def test_get_firstUrn(self):
        """Check get Label"""
        # Need to parse with Citation and parse individually or simply check for some equality
        data = self.app.get("/cts?request=GetFirstUrn&urn=urn:cts:latinLit:phi1294.phi002.perseus-lat2:1").data.decode()

        self.assertIn(
            "<urn>urn:cts:latinLit:phi1294.phi002.perseus-lat2:1.pr</urn>", data, "First URN is displayed"
        )
        self.assertEqual(
            (data.startswith("<GetFirstUrn"), data.endswith("</GetFirstUrn>")), (True, True), "Nodes are Correct"
        )


class DTSModule:
    def assertJsonLdEqual(self, expected, actual, message=None):
        self.assertEqual(expand(expected), expand(actual), message)

    def assertHeadersEqual(self, expected, actual, message=None):
        expected = link_header.parse(expected).to_py()

        def sort_key(it):
            return "-".join(it[1][0])

        expected = [(urltools.normalize(link[0]), link[1]) for link in expected]
        actual = [(urltools.normalize(link[0]), link[1]) for link in actual]

        self.assertEqual(
            sorted(expected, key=sort_key),
            sorted(actual, key=sort_key),
            message
        )

    def test_dts_collection_route(self):
        """ Check that DTS Main collection works """
        response = self.app.get("/dts/collections")
        data = json.loads(response.data.decode())

        self.maxDiff = None
        self.assertJsonLdEqual(
            data, dts_coll_mockups.response_defaultTic, "Main Collection should export as JSON DTS STD"
        )
        self.assertEqual(
            response.status_code, 200, "Answer code should be correct"
        )
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"], "*"
        )

    def test_dts_collection_target_route(self):
        """ Check that DTS Main collection works """
        response = self.app.get("/dts/collections?id=urn:cts:latinLit:phi1294")
        data = json.loads(response.data.decode())

        self.maxDiff = None
        self.assertJsonLdEqual(
            data, dts_coll_mockups.response_phi1294, "Main Collection should export as JSON DTS STD"
        )
        self.assertEqual(
            response.status_code, 200, "Answer code should be correct"
        )
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"], "*"
        )
        self.assertEqual(
            "urn:cts:latinLit:phi1294", data["@id"], "Label should be there"
        )

    def test_dts_collection_parent(self):
        response = self.app.get("/dts/collections?id=urn:cts:latinLit:phi1294.phi002&nav=parents")
        data = json.loads(response.data.decode())

        self.maxDiff = None
        self.assertJsonLdEqual(
            data, dts_coll_mockups.response_phi1294_phi002_parent, "Main Collection should export as JSON DTS STD"
        )
        self.assertEqual(
            response.status_code, 200, "Answer code should be correct"
        )
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"], "*"
        )

    def test_dts_navigation_simple(self):
        response = self.app.get("/dts/navigation?id=urn:cts:latinLit:phi1294.phi002.perseus-lat2")

        data = json.loads(response.data.decode())
        normalize_uri_key(data, "passage")
        normalize_uri_key(data, "@id")

        self.maxDiff = None

        self.assertJsonLdEqual(
            dts_refs_mockups.phi1294_response, data, "Main Collection should export as JSON DTS STD"
        )
        self.assertEqual(
            response.status_code, 200, "Answer code should be correct"
        )
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"], "*"
        )

    def test_dts_navigation_group_by(self):
        """ Ensure that groupBy works in DTS Navigation Route"""
        response = self.app.get("/dts/navigation?id=urn:cts:latinLit:phi1294.phi002.perseus-lat2&groupBy=2")
        data = json.loads(response.data.decode())
        normalize_uri_key(data, "passage")
        normalize_uri_key(data, "@id")

        self.maxDiff = None
        self.assertJsonLdEqual(
            dts_refs_mockups.phi1294_group_by_response, data, "Main Collection should export as JSON DTS STD"
        )
        self.assertEqual(
            response.status_code, 200, "Answer code should be correct"
        )
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"], "*"
        )

    def test_dts_navigation_group_by_with_start_end(self):
        """ Ensure that groupBy works and level is influenced by the level of the ref in DTS Navigation Route"""
        response = self.app.get("/dts/navigation?id=urn:cts:latinLit:phi1294.phi002.perseus-lat2"
                                "&groupBy=100"
                                "&start=1&end=2")
        data = json.loads(response.data.decode())

        normalize_uri_key(data, "passage")
        normalize_uri_key(data, "@id")

        self.maxDiff = None
        self.assertJsonLdEqual(
            dts_refs_mockups.phi1294_group_by_response_start_end, data, "Main Collection should export as JSON DTS STD"
        )
        self.assertEqual(
            response.status_code, 200, "Answer code should be correct"
        )
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"], "*"
        )

    def test_dts_navigation_group_by_with_level(self):
        """ Ensure that groupBy works and level is influenced by the level of the ref in DTS Navigation Route"""
        response = self.app.get("/dts/navigation?id=urn:cts:latinLit:phi1294.phi002.perseus-lat2"
                                "&groupBy=100"
                                "&ref=1"
                                "&level=3")
        data = json.loads(response.data.decode())

        normalize_uri_key(data, "passage")
        normalize_uri_key(data, "@id")

        self.maxDiff = None
        self.assertJsonLdEqual(
            dts_refs_mockups.phi1294_group_by_response_ref_level_2, data,
            "Main Collection should export as JSON DTS STD"
        )
        self.assertEqual(
            response.status_code, 200, "Answer code should be correct"
        )
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"], "*"
        )

    def test_dts_navigation_errors(self):
        """ Ensure that errors are returned correctly """
        self.maxDiff = 50000
        response = self.app.get("/dts/navigation?id=urn:cts:latinLit:phi1294.phi002.perseus-lat2"
                                "&ref=1.pr.1")

        data = json.loads(response.data.decode())
        self.assertJsonLdEqual(
            {'@type': 'Status', 'statusCode': 404, '@context': 'http://www.w3.org/ns/hydra/context.jsonld',
             'title': 'InvalidLevel', 'description': ' Invalid value for level parameter in Navigation Endpoint request '},
            data,
            "Information should be shown about the error"
        )

    def test_dts_document(self):

        response = self.app.get("/dts/document?id=urn:cts:latinLit:phi1294.phi002.perseus-lat2"
                                "&ref=1.1")
        data = response.data.decode()
        headers = response.headers
        xml = xmlparser(data)
        self.assertEqual(
            [
                "Hic est quem legis ille, quem requiris,",
                "Toto notus in orbe Martialis",
                "Argutis epigrammaton libellis:",
                "Cui, lector studiose, quod dedisti",
                "Viventi decus atque sentienti,",
                "Rari post cineres habent poetae."
            ],
            [
                x.strip()
                for x in xml.xpath(".//tei:l/text()", namespaces=XPATH_NAMESPACES)
                if x.strip()
            ],  # Stripping for equality and removing empty line
            "The text of lines should match"
        )

        self.assertHeadersEqual(
            headers["Link"],
            [
                ['/dts/document?id=urn%3Acts%3AlatinLit%3Aphi1294.phi002.perseus-lat2&ref=1.2', [['rel', 'next']]],
                ['/dts/document?id=urn%3Acts%3AlatinLit%3Aphi1294.phi002.perseus-lat2&ref=1', [['rel', 'up']]],
                ['/dts/navigation?id=urn%3Acts%3AlatinLit%3Aphi1294.phi002.perseus-lat2&ref=1.1', [['rel', 'contents']]],
                ['/dts/document?id=urn%3Acts%3AlatinLit%3Aphi1294.phi002.perseus-lat2&ref=1.pr', [['rel', 'prev']]],
                ['/dts/collections?id=urn%3Acts%3AlatinLit%3Aphi1294.phi002.perseus-lat2', [['rel', 'collection']]]
            ]
        )

    def test_dts_document_start_end(self):

        response = self.app.get("/dts/document?id=urn:cts:latinLit:phi1294.phi002.perseus-lat2"
                                "&start=1.1.3&end=1.1.4")
        data = response.data.decode()
        headers = response.headers
        xml = xmlparser(data)
        self.assertEqual(
            [
                "Argutis epigrammaton libellis:",
                "Cui, lector studiose, quod dedisti",
            ],
            [
                x.strip()
                for x in xml.xpath(".//tei:l/text()", namespaces=XPATH_NAMESPACES)
                if x.strip()
            ],  # Stripping for equality and removing empty line
            "The text of lines should match"
        )

        self.maxDiff = None
        self.assertHeadersEqual(
            headers["Link"],
            [
                ['/dts/document?id=urn%3Acts%3AlatinLit%3Aphi1294.phi002.perseus-lat2&start=1.1.5&end=1.1.6', [['rel', 'next']]],
                ['/dts/document?id=urn%3Acts%3AlatinLit%3Aphi1294.phi002.perseus-lat2&ref=1.1', [['rel', 'up']]],
                ['/dts/navigation?id=urn%3Acts%3AlatinLit%3Aphi1294.phi002.perseus-lat2&start=1.1.3&end=1.1.4', [['rel', 'contents']]],
                ['/dts/document?id=urn%3Acts%3AlatinLit%3Aphi1294.phi002.perseus-lat2&start=1.1.1&end=1.1.2', [['rel', 'prev']]],
                ['/dts/collections?id=urn%3Acts%3AlatinLit%3Aphi1294.phi002.perseus-lat2', [['rel', 'collection']]]
            ]
        )


class LoggingModule:
    def setUp(self):
        SetupModule.setUp(self)
        self.nautilus.resolver.parse(["./tests/test_data/latinLit"])
        self.nautilus.logger.setLevel(logging.INFO)
        self.nautilus.logger.disabled = False
        logassert.setup(self, self.nautilus.logger.name)

    def test_UnknownCollection_request(self):
        """Check get Label"""
        self.app.debug = True
        # Need to parse with Citation and parse individually or simply check for some equality
        data = self.app.get("/cts?request=GetCapabilities&urn=urn:cts:latinLit:phi1295").data.decode()
        self.assertIn(
            "urn:cts:latinLit:phi1295 is not part of this inventory", data, "Error message should be displayed"
        )
        self.assertIn(
            "UnknownCollection", data, "Error name should be displayed"
        )

        self.assertLogged("CTS error thrown UnknownCollection for "
                          "request=GetCapabilities&urn=urn:cts:latinLit:phi1295 "
                          "(urn:cts:latinLit:phi1295 is not part of this inventory)")

        data = self.app.get("/cts?request=GetPassage&urn=urn:cts:latinLit:phi1294.phi003").data.decode()
        self.assertIn(
            "urn:cts:latinLit:phi1294.phi003 is not part of this inventory", data, "Error message should be displayed"
        )
        self.assertIn(
            "UnknownCollection", data, "Error name should be displayed"
        )

    def test_dts_UnknownCollection_request(self):
        """Check get Label"""
        # Need to parse with Citation and parse individually or simply check for some equality
        data = json.loads(self.app.get("/dts/collections?id=urn:cts:latinLit:phi1295").data.decode())
        self.assertIn(
            "Resource requested is not found", data["description"], "Error message should be displayed"
        )
        self.assertIn(
            "UnknownCollection", data["title"], "Error name should be displayed"
        )
        data = json.loads(self.app.get("/dts/collections?id=urn:cts:latinLit:phi1294.phi003").data.decode())
        self.assertIn(
            "Resource requested is not found", data["description"], "Error message should be displayed"
        )
        self.assertIn(
            "UnknownCollection", data["title"], "Error name should be displayed"
        )
        self.assertLogged("DTS error thrown UnknownCollection for /dts/collections "
                          "( Resource requested is not found ) "
                          "(Debug : Resource urn:cts:latinLit:phi1294.phi003 not found)")

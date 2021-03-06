"""
    Copyright (C) 2017, ContraxSuite, LLC

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as
    published by the Free Software Foundation, either version 3 of the
    License, or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

    You can also be released from the requirements of the license by purchasing
    a commercial license from ContraxSuite, LLC. Buying such a license is
    mandatory as soon as you develop commercial activities involving ContraxSuite
    software without disclosing the source code of your own applications.  These
    activities include: offering paid services to customers as an ASP or "cloud"
    provider, processing documents on the fly in a web application,
    or shipping ContraxSuite within a closed source product.
"""
# -*- coding: utf-8 -*-

import datetime
from collections import defaultdict
from typing import List, Set, Dict, Type, Optional, Tuple

from django.db import transaction
from lexnlp.extract.en import (
    amounts, citations, copyright, courts, dates, distances, definitions,
    durations, geoentities, money, percents, ratios, regulations, trademarks, urls, dict_entities)
from lexnlp.extract.en.entities.nltk_maxent import get_companies
from lexnlp.nlp.en.tokens import get_stems, get_token_list

from apps.common.log_utils import ProcessLogger
from apps.document.app_vars import STRICT_PARSE_DATES
from apps.document.models import TextUnitTag
from apps.extract import dict_data_cache
from apps.extract.models import (
    AmountUsage, CitationUsage, CopyrightUsage, CourtUsage, CurrencyUsage,
    DateDurationUsage, DateUsage, DefinitionUsage, DistanceUsage,
    GeoAliasUsage, GeoEntityUsage, PercentUsage, RatioUsage, RegulationUsage,
    Party, PartyUsage, TermUsage, TrademarkUsage, UrlUsage, Usage, DocumentTermUsage)
from settings import DEFAULT_FLOAT_PRECIZION

__author__ = "ContraxSuite, LLC; LexPredict, LLC"
__copyright__ = "Copyright 2015-2020, ContraxSuite, LLC"
__license__ = "https://github.com/LexPredict/lexpredict-contraxsuite/blob/1.5.0/LICENSE"
__version__ = "1.5.0"
__maintainer__ = "LexPredict, LLC"
__email__ = "support@contraxsuite.com"


class ParseResults:
    __slots__ = ['usage_entities', 'text_unit_tags']

    def __init__(self, usage_entities: Dict[Type[Usage], List[Usage]],
                 text_unit_tags: Optional[Set[str]] = None) -> None:
        super().__init__()
        self.usage_entities = dict(
            usage_entities) if usage_entities is not None else dict()  # type: Dict[Type[Usage], List[Usage]]
        self.text_unit_tags = set(text_unit_tags) if text_unit_tags is not None else set()  # type: Set[str]


class LocationResults:

    def __init__(self) -> None:
        self.tags = defaultdict(set)  # type: Dict[int, Set[str]]
        self.located_usage_entities = defaultdict(list)  # type: Dict[Type[Usage], List]
        self.processed_usage_entity_classes = set()  # type: Set[Type[Usage]]
        self.processed_text_unit_ids = set()  # type: Set[int]

    def collect(self, locator: 'Locator', text_unit_id, parse_results: ParseResults):
        self.processed_text_unit_ids.add(text_unit_id)
        self.processed_usage_entity_classes.update(locator.locates_usage_model_classes)
        if parse_results:
            if parse_results.text_unit_tags:
                self.tags.update({text_unit_id: tag_str for tag_str in parse_results.text_unit_tags})
            if parse_results.usage_entities:
                self.tags[text_unit_id].add(locator.code)
                for k, v in parse_results.usage_entities.items():
                    self.located_usage_entities[k].extend(v)

    def save(self, log: ProcessLogger, user_id):
        try:
            with transaction.atomic():
                if self.processed_text_unit_ids:
                    TextUnitTag.objects.filter(text_unit_id__in=self.processed_text_unit_ids).delete()
                    for entity_class in self.processed_usage_entity_classes:
                        entity_class.objects.filter(text_unit_id__in=self.processed_text_unit_ids).delete()

                count = 0
                for entity_class, entities in self.located_usage_entities.items():  # type: Type[Usage], List[Usage]
                    if entities:
                        entity_class.objects.bulk_create(entities, ignore_conflicts=True)
                        count += len(entities)

                tag_models = list()
                from apps.document.app_vars import LOCATE_TEXTUNITTAGS
                if LOCATE_TEXTUNITTAGS.val:
                    for text_unit_id, tags in self.tags.items():
                        for tag in tags:
                            tag_models.append(TextUnitTag(user_id=user_id,
                                                          text_unit_id=text_unit_id,
                                                          tag=tag))
                    TextUnitTag.objects.bulk_create(tag_models, ignore_conflicts=True)
                log.info(
                    'Stored {0} usage entities and {1} tags for {2} text units'.format(
                        count, len(tag_models), len(self.processed_text_unit_ids)))
        except Exception as e:
            entities_str = '\n'.join([str(e) for e in self.processed_usage_entity_classes])
            log.error(f'Unable to store location results.\n'
                      f'Text unit ids: {self.processed_text_unit_ids}\n'
                      f'Usage models caused the problem:\n{entities_str}', exc_info=e)
        self.save_summary(log, user_id)

    def save_summary(self, log: ProcessLogger, user_id):
        # save DocumentTermUsage
        if self.located_usage_entities and TermUsage in self.located_usage_entities:
            term_usages = self.located_usage_entities[TermUsage]
            # update DocumentTermUsage records
            doc_term_usgs = {}  # type: Dict[Tuple[int, int], DocumentTermUsage]
            for tu in term_usages:  # type: TermUsage
                key = (tu.text_unit.document_id, tu.term.pk,)
                doc_usg = doc_term_usgs.get(key)
                if doc_usg:
                    doc_usg.count += 1
                else:
                    doc_usg = DocumentTermUsage()
                    doc_usg.document_id = tu.text_unit.document_id
                    doc_usg.term_id = tu.term.pk
                    doc_usg.count = 1
                    doc_term_usgs[key] = doc_usg
            if doc_term_usgs:
                doc_term_usgs_lst = [v for _, v in doc_term_usgs.items()]
                try:
                    with transaction.atomic():
                        DocumentTermUsage.objects.bulk_create(doc_term_usgs_lst, ignore_conflicts=True)
                except Exception as e:
                    log.error(f'Unable to store {len(doc_term_usgs)} DocumentTermUsage records.\n',
                              exc_info=e)


class Locator:
    STRICT_DATES_PTR = 'strict_dates'

    code = None

    locates_usage_model_classes = []

    def parse(self, log: ProcessLogger, text: str, text_unit_id: int, text_unit_lang: str, **kwargs) -> ParseResults:
        pass

    def try_parsing(self, log: ProcessLogger, locate_results: LocationResults, text: str,
                    text_unit_id: int, text_unit_lang: str, **kwargs):
        try:
            parse_results = self.parse(log, text, text_unit_id, text_unit_lang, **kwargs)  # type: ParseResults
            if parse_results:
                locate_results.collect(self, text_unit_id, parse_results)
        except Exception as e:
            log.error(f'Exception caught while trying to run locator on a text unit.\n'
                      f'Locator: {self.__class__.__name__}\n'
                      f'Text unit id: {text_unit_id}\n'
                      f'Text: {text[:1024]}\n'
                      f'Text unit language: {text_unit_lang}\n', exc_info=e)


class AmountLocator(Locator):
    code = 'amount'

    locates_usage_model_classes = [AmountUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        precision = DEFAULT_FLOAT_PRECIZION
        found = list(amounts.get_amount_annotations(text,
                                                    extended_sources=False,
                                                    float_digits=precision))
        if found:
            unique = set(found)
            return ParseResults({AmountUsage: [AmountUsage(text_unit_id=text_unit_id,
                                                           amount=item.value,
                                                           amount_str=item.text[:300] if item.text else None,
                                                           count=found.count(item)
                                                           ) for item in unique]})


class CitationLocator(Locator):
    code = 'citation'
    locates_usage_model_classes = [CitationUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        found = list(citations.get_citation_annotations(text))
        if found:
            unique = set(found)
            return ParseResults({CitationUsage: [CitationUsage(text_unit_id=text_unit_id,
                                                               volume=item.volume,
                                                               reporter=item.reporter,
                                                               reporter_full_name=item.reporter_full_name,
                                                               page=item.page,
                                                               page2=item.page_range,
                                                               court=item.court,
                                                               year=item.year,
                                                               citation_str=item.source,
                                                               count=found.count(item)) for item in unique]})


class CourtLocator(Locator):
    code = 'court'

    locates_usage_model_classes = [CourtUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, text_unit_lang, **kwargs) -> ParseResults:
        court_config = dict_data_cache.get_court_config()
        found = [dict_entities.get_entity_id(i[0])
                 for i in courts.get_courts(text,
                                            court_config_list=court_config,
                                            text_languages=[text_unit_lang])]
        if found:
            unique = set(found)
            return ParseResults({CourtUsage: [CourtUsage(text_unit_id=text_unit_id,
                                                         court_id=court_id,
                                                         count=found.count(court_id)) for court_id in unique]})


class DistanceLocator(Locator):
    code = 'distance'

    locates_usage_model_classes = [DistanceUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        precision = DEFAULT_FLOAT_PRECIZION
        found = list(distances.get_distance_annotations(text, float_digits=precision))
        if found:
            unique = set(found)
            return ParseResults({DistanceUsage: [DistanceUsage(text_unit_id=text_unit_id,
                                                               amount=item.amount,
                                                               amount_str=item.text,
                                                               distance_type=item.distance_type,
                                                               count=found.count(item)) for item in unique]})


class DateLocator(Locator):
    code = 'date'

    locates_usage_model_classes = [DateUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        strict = kwargs.get(Locator.STRICT_DATES_PTR, STRICT_PARSE_DATES.val)
        found = list(dates.get_date_annotations(
            text,
            strict=strict))
        if found:
            _all = [i.date.date() if isinstance(i.date, datetime.datetime)
                    else i.date for i in found]
            return ParseResults({DateUsage: [DateUsage(text_unit_id=text_unit_id,
                                                       date=item,
                                                       count=_all.count(item)) for item in set(_all)]})


class DefinitionLocator(Locator):
    code = 'definition'

    locates_usage_model_classes = [DefinitionUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        found = definitions.get_definition_list_in_sentence((0, len(text), text,))
        if found:
            unique = set(found)
            return ParseResults({DefinitionUsage: [DefinitionUsage(text_unit_id=text_unit_id,
                                                                   definition=item.name,
                                                                   count=found.count(item)
                                                                   ) for item in unique]})


class DurationLocator(Locator):
    code = 'duration'

    locates_usage_model_classes = [DateDurationUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        precision = DEFAULT_FLOAT_PRECIZION
        found = durations.get_duration_annotations_list(
            text, float_digits=precision)
        if found:
            unique = set(found)
            return ParseResults({DateDurationUsage: [DateDurationUsage(text_unit_id=text_unit_id,
                                                                       amount=item.amount,
                                                                       amount_str=item.text,
                                                                       duration_type=item.duration_type,
                                                                       duration_days=item.duration_days,
                                                                       count=found.count(item)
                                                                       ) for item in unique]})


class CurrencyLocator(Locator):
    code = 'currency'

    locates_usage_model_classes = [CurrencyUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        found = list(money.get_money_annotations(text,
                                                 float_digits=DEFAULT_FLOAT_PRECIZION))
        if found:
            unique = set(found)
            return ParseResults({CurrencyUsage: [CurrencyUsage(text_unit_id=text_unit_id,
                                                               amount=item.amount,
                                                               amount_str=item.text,
                                                               currency=item.currency,
                                                               count=found.count(item)
                                                               ) for item in unique]})


class PartyLocator(Locator):
    code = 'party'

    locates_usage_model_classes = [PartyUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> Optional[ParseResults]:
        # Here we override saving logic to workaround race conditions on party creation vs party usage saving
        PartyUsage.objects.filter(text_unit_id=text_unit_id).delete()
        found = list(get_companies(text, count_unique=True, detail_type=True, name_upper=True))
        if found:
            for _party in found:
                name, _type, type_abbr, type_label, type_desc, count = _party
                defaults = dict(
                    type=_type,
                    type_label=type_label,
                    type_description=type_desc
                )
                party, created = Party.objects.get_or_create(
                    name=name,
                    type_abbr=type_abbr or '',
                    defaults=defaults
                )

                PartyUsage(text_unit_id=text_unit_id,
                           party=party,
                           count=count).save()
            return None


class PercentLocator(Locator):
    code = 'percent'

    locates_usage_model_classes = [PercentUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        found = list(percents.get_percent_annotations(text,
                                                      float_digits=DEFAULT_FLOAT_PRECIZION))
        if found:
            unique = set(found)
            return ParseResults({PercentUsage: [PercentUsage(text_unit_id=text_unit_id,
                                                             amount=item.amount,
                                                             amount_str=item.text,
                                                             unit_type=item.sign,
                                                             total=item.fraction,
                                                             count=found.count(item)) for item in unique]})


class RatioLocator(Locator):
    code = 'ratio'

    locates_usage_model_classes = [RatioUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        found = list(ratios.get_ratio_annotations(text,
                                                  float_digits=DEFAULT_FLOAT_PRECIZION))
        if found:
            unique = set(found)
            return ParseResults({RatioUsage: [RatioUsage(text_unit_id=text_unit_id,
                                                         amount=item.left,
                                                         amount2=item.right,
                                                         amount_str=item.text,
                                                         total=item.ratio,
                                                         count=found.count(item)) for item in unique]})


class RegulationLocator(Locator):
    code = 'regulation'

    locates_usage_model_classes = [RegulationUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        found = list(regulations.get_regulation_annotations(text))
        if found:
            unique = set(found)
            return ParseResults({RegulationUsage: [RegulationUsage(text_unit_id=text_unit_id,
                                                                   regulation_type=item.source,
                                                                   regulation_name=item.name,
                                                                   count=found.count(item)) for item in unique]})


class CopyrightLocator(Locator):
    code = 'copyright'
    locates_usage_model_classes = [CopyrightUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        # TODO: what's the logic behind [:200] ... < 100 ?
        found = list(copyright.get_copyright_annotations(text, return_sources=True))
        if found:
            unique = set(found)
            return ParseResults({CopyrightUsage: [CopyrightUsage(text_unit_id=text_unit_id,
                                                                 year=item.date,
                                                                 name=item.name[:200],
                                                                 copyright_str=item.text[:200],
                                                                 count=found.count(item)
                                                                 ) for item in unique if len(item.name) < 100]})


class TrademarkLocator(Locator):
    code = 'trademark'
    locates_usage_model_classes = [TrademarkUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        found = [t.trademark for t in trademarks.get_trademark_annotations(text)]
        if found:
            unique = set(found)
            return ParseResults({TrademarkUsage: [TrademarkUsage(text_unit_id=text_unit_id,
                                                                 trademark=item,
                                                                 count=found.count(item)
                                                                 ) for item in unique]})


class UrlLocator(Locator):
    code = 'url'

    locates_usage_model_classes = [UrlUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        found = [u.url for u in urls.get_url_annotations(text)]
        if found:
            unique = set(found)
            return ParseResults({UrlUsage: [UrlUsage(text_unit_id=text_unit_id,
                                                     source_url=item,
                                                     count=found.count(item)) for item in unique]})


class GeoEntityLocator(Locator):
    code = 'geoentity'

    locates_usage_model_classes = [GeoEntityUsage, GeoAliasUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, text_unit_lang, **kwargs) -> ParseResults:
        priority = kwargs.get('priority', True)
        geo_config = dict_data_cache.get_geo_config()
        entity_alias_pairs = list(geoentities.get_geoentities(text,
                                                              geo_config,
                                                              text_languages=[text_unit_lang],
                                                              priority=priority))

        entity_ids = [dict_entities.get_entity_id(entity) for entity, _alias in entity_alias_pairs]
        if entity_ids:
            unique_entities = set(entity_ids)
            alias_ids = [dict_entities.get_alias_id(alias) for _entity, alias in entity_alias_pairs]
            unique_aliases = set(alias_ids)

            return ParseResults({
                GeoEntityUsage: [GeoEntityUsage(text_unit_id=text_unit_id,
                                                entity_id=idd,
                                                count=entity_ids.count(idd)) for idd in unique_entities],
                GeoAliasUsage: [GeoAliasUsage(text_unit_id=text_unit_id,
                                              alias_id=idd,
                                              count=alias_ids.count(idd)) for idd in unique_aliases if idd]})


class TermLocator(Locator):
    code = 'term'
    locates_usage_model_classes = [TermUsage]

    def parse(self, log: ProcessLogger, text, text_unit_id, _text_unit_lang, **kwargs) -> ParseResults:
        project_id = kwargs.get('project_id')
        term_stems = dict_data_cache.get_term_config(project_id)
        text_stems = ' %s ' % ' '.join(get_stems(text, lowercase=True))
        text_tokens = get_token_list(text, lowercase=True)
        term_usages = []
        for stemmed_term, data in term_stems.items():
            # stem not found in text
            if stemmed_term not in text_stems:
                continue
            # if stem has 1 variant only
            if data['length'] == 1:
                count = text_stems.count(stemmed_term)
                if count:
                    term_data = list(data['values'][0])
                    term_data.append(count)
                    term_usages.append(term_data)
            # case when f.e. stem "respons" is equal to multiple terms
            # ["response", "responsive", "responsibility"]
            else:
                for term_data in data['values']:
                    term_data = list(term_data)
                    count = text_tokens.count(term_data[0])
                    if count:
                        term_data.append(count)
                        term_usages.append(term_data)
                        # TODO: "responsibilities"

        return ParseResults({TermUsage: [
            TermUsage(text_unit_id=text_unit_id,
                      term_id=pk,
                      count=count) for _, pk, count in term_usages]})


LOCATOR_CLASSES = [AmountLocator, CitationLocator, CopyrightLocator, CourtLocator, CurrencyLocator,
                   DurationLocator, DateLocator, DefinitionLocator, DistanceLocator, GeoEntityLocator,
                   PercentLocator, RatioLocator, RegulationLocator, PartyLocator, TermLocator, TrademarkLocator,
                   UrlLocator]

LOCATORS = {locator_class.code: locator_class() for locator_class in LOCATOR_CLASSES}  # type: Dict[str, Locator]

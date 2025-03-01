import os
import re
from datetime import datetime, timedelta

import pandas as pd

from cowidev.utils.clean import clean_count, clean_string, clean_date
from cowidev.utils.web.scraping import get_soup
from cowidev.vax.utils.incremental import merge_with_current_data


class Vietnam:
    location: str = "Vietnam"
    source_url: str = "https://moh.gov.vn/tin-tong-hop"
    regex: dict = {
        "date": r"Bản tin dịch COVID-19 ngày (\d{1,2}/\d{1,2}) của Bộ",
        "metrics": (
            r"Trong ngày \d{1,2}/\d{1,2} có [\.\d]+ liều (?:vắc xin phòng|vaccine|vaccine phòng) COVID-19 được tiêm(?:.*)?. Như vậy, tổng số liều (?:vắc xin|vaccine|vaccien) đã được tiêm là ([\d\.]+) liều, trong đó tiêm 1 mũi là ([\d\.]+) liều, tiêm mũi 2 là ([\d\.]+) liều"
        ),
    }

    def read(self, last_updated: str) -> pd.DataFrame:
        soup = get_soup(self.source_url)
        news_info_all = self._parse_news_info(soup)
        records = []
        for news_info in news_info_all:
            # print(news_info)
            if news_info["date"] < last_updated:
                break
            records.append(self._parse_metrics(news_info))
        return pd.DataFrame(records)

    def _parse_news_info(self, soup):
        news = soup.find_all(class_="page-list-news")
        news = list(filter(lambda x: re.search(self.regex["date"], x.p.text), news))
        return [{"link": n.a.get("href"), "date": self._parse_date(n.p.text)} for n in news]

    def _parse_date(self, text: str):
        dt_raw = re.search(self.regex["date"], text).group(1) + f"/{datetime.now().year}"
        dt = datetime.strptime(dt_raw, "%d/%m/%Y") - timedelta(days=1)
        return clean_date(dt)

    def _parse_metrics(self, news_info: dict):
        soup = get_soup(news_info["link"])
        text = clean_string(soup.text)
        metrics = re.search(self.regex["metrics"], text).group(1, 2, 3)
        return {
            "total_vaccinations": clean_count(metrics[0]),
            "people_vaccinated": clean_count(metrics[1]),
            "people_fully_vaccinated": clean_count(metrics[2]),
            "source_url": news_info["link"],
            "date": news_info["date"],
        }

    def pipe_clean_source_url(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.assign(source_url=df.source_url.apply(lambda x: x.split("?")[0]))

    def pipe_metadata(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.assign(
            location=self.location,
            vaccine="Moderna, Oxford/AstraZeneca, Pfizer/BioNTech, Sinopharm/Beijing, Sputnik V",
        )

    def pipeline(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.pipe(self.pipe_metadata).pipe(self.pipe_clean_source_url)

    def export(self, paths):
        output_file = paths.tmp_vax_out(self.location)
        last_update = pd.read_csv(output_file).date.max()
        df = self.read(last_update)
        if df is not None:
            df = df.pipe(self.pipeline)
            df = merge_with_current_data(df, output_file)
            df.to_csv(output_file, index=False)


def main(paths):
    Vietnam().export(paths)


if __name__ == "__main__":
    main()

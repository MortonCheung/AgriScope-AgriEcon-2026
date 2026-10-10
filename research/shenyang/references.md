# 数据来源与参考文献（沈阳研究 v2）

> 本文件列出 v2 使用的全部来源。**公开来源（URL）与本地留档严格分离**：
> 下表只给出互联网可访问的公开地址；本地快照路径仅存于内部 provenance
> （`research_v2/sources/source_registry.csv` 的 `local_snapshot` 列），**不对外展示**。

## 一、数据来源

| 来源 ID | 名称 | 发布方 | 时间范围 | 公开地址 | 等级 |
|---|---|---|---|---|---|
| `SRC-SY-CLZ` | 沈阳菜篮子信息发布平台（批发/超市/集市日度价格与批发成交量） | 沈阳市发展和改革委员会 | 2020-01-02~2026-09-21（本项目使用 2021-01-01~2026-09-14） | [https://www.lnsyjgjc.com/](https://www.lnsyjgjc.com/) | A |
| `SRC-LN-NYNC` | 辽宁省农业农村厅 农产品信息·价格简讯（含省级批发均价与区县最高/最低价） | 辽宁省农业农村厅 | 2021-03-11~2026-09-17 | [http://nync.ln.gov.cn/](http://nync.ln.gov.cn/) | A |
| `SRC-MOA-PFSC` | 全国农产品批发市场价格信息系统（市场目录与地区坐标） | 农业农村部 | 静态目录 | [https://pfsc.agri.cn/](https://pfsc.agri.cn/) | A |
| `SRC-OM-ERA5` | Open-Meteo Historical Weather API（ERA5 / ERA5-Land 再分析网格） | Open-Meteo（数据来自 Copernicus/ECMWF ERA5） | 1940 至今（本项目使用 2015-01-01~2026-09-14） | [https://archive-api.open-meteo.com/v1/archive](https://archive-api.open-meteo.com/v1/archive) | A |
| `SRC-OM-BASELINE` | Open-Meteo 1991-2020 逐日气候基线（沈阳） | Open-Meteo（ERA5） | 1991-01-01~2020-12-31 | [https://archive-api.open-meteo.com/v1/archive](https://archive-api.open-meteo.com/v1/archive) | A |
| `SRC-EVT-DERIVED` | 沈阳极端天气事件（ERA5 日值阈值算法派生） | 本项目派生（基于 Open-Meteo ERA5） | 2021-01-01~2026-09-14（沈阳 20 起） | [https://archive-api.open-meteo.com/v1/archive](https://archive-api.open-meteo.com/v1/archive) | B |
| `SRC-SY-YB` | 《沈阳统计年鉴》（农业章 3-4 农作物播种面积 / 3-5 农作物总产量 / 3-6 农作物单产量，均为分区县表） | 沈阳市统计局 / 国家统计局沈阳调查队 | 数据年 2018~2024（本项目 7 卷） | [https://tjj.shenyang.gov.cn/sjfb/ndsj/](https://tjj.shenyang.gov.cn/sjfb/ndsj/) | A |
| `SRC-SY-BULLETIN` | 沈阳市国民经济和社会发展统计公报（历年） | 沈阳市统计局 / 国家统计局沈阳调查队 | 2015~2025 | [https://www.shenyang.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/](https://www.shenyang.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/) | A |
| `SRC-KP-YB` | 《康平县国民经济统计资料汇编》2016/2017 卷（国民经济主要指标·四、农村经济） | 康平县统计局 | 2015~2017（补充） | [https://www.kangping.gov.cn/zwgk/fdzdgknr/tjxx/tjnj/](https://www.kangping.gov.cn/zwgk/fdzdgknr/tjxx/tjnj/) | B |
| `SRC-DIST-新民市` | 新民市国民经济和社会发展统计公报（历年） | 新民市人民政府 / 统计局 | 2018~2025 | [https://www.xinmin.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/](https://www.xinmin.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/) | B |
| `SRC-DIST-辽中区` | 辽中区国民经济和社会发展统计公报（历年） | 辽中区人民政府 / 统计局 | 2018~2025 | [https://www.liaozhong.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/](https://www.liaozhong.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/) | B |
| `SRC-DIST-康平县` | 康平县国民经济和社会发展统计公报（历年） | 康平县人民政府 / 统计局 | 2018~2025 | [https://www.kangping.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/](https://www.kangping.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/) | B |
| `SRC-DIST-法库县` | 法库县国民经济和社会发展统计公报（历年） | 法库县人民政府 / 统计局 | 2018~2025 | [https://www.faku.gov.cn/zfxxgk/fdzdgknr/tjxx/tjgb/](https://www.faku.gov.cn/zfxxgk/fdzdgknr/tjxx/tjgb/) | B |
| `SRC-DIST-沈北新区` | 沈北新区国民经济和社会发展统计公报（历年） | 沈北新区人民政府 / 统计局 | 2018~2025 | [https://www.nsy.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/](https://www.nsy.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/) | B |
| `SRC-DIST-苏家屯区` | 苏家屯区国民经济和社会发展统计公报（历年） | 苏家屯区人民政府 / 统计局 | 2018~2025 | [https://www.sjtq.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/](https://www.sjtq.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/) | B |
| `SRC-DIST-浑南区` | 浑南区国民经济和社会发展统计公报（历年） | 浑南区人民政府 / 统计局 | 2018~2025 | [http://www.hunnan.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/](http://www.hunnan.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/) | B |
| `SRC-DIST-于洪区` | 于洪区国民经济和社会发展统计公报（历年） | 于洪区人民政府 / 统计局 | 2018~2025 | [https://www.syyh.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/](https://www.syyh.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/) | B |
| `SRC-DST-COORD` | 区县代表点经纬度（农业农村部 pfsc 地区接口返回的行政中心坐标） | 农业农村部 全国农产品批发市场价格信息系统 | 静态 | [https://pfsc.agri.cn/](https://pfsc.agri.cn/) | A |

## 二、参考文献

共 43 条。全部 DOI 已通过 Crossref API 批量核验（34/34 通过）；
中文期刊 DOI 经 doi.org 解析至中国 DOI 注册机构（chndoi）。

| # | 文献 | 类型 | 用途 | DOI / 链接 |
|---|---|---|---|---|
| 1 | Heteroskedasticity and Autocorrelation Consistent Covariance Matrix Estimation（Andrews, D. W. K.，1991，*Econometrica*） | 方法 | 用于 METHOD | [https://doi.org/10.2307/2938229](https://doi.org/10.2307/2938229) |
| 2 | How Much Should We Trust Differences-In-Differences Estimates?（Bertrand, M.; Duflo, E.; Mullainathan, S.，2004，*The Quarterly Journal of Economics*） | 方法 | 用于 METHOD | [https://doi.org/10.1162/003355304772839588](https://doi.org/10.1162/003355304772839588) |
| 3 | Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing（Benjamini, Y.; Hochberg, Y.，1995，*Journal of the Royal Statistical Society: Series B*） | 方法 | 用于 METHOD | [https://doi.org/10.1111/j.2517-6161.1995.tb02031.x](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x) |
| 4 | The control of the false discovery rate in multiple testing under dependency（Benjamini, Y.; Yekutieli, D.，2001，*The Annals of Statistics*） | 方法 | 用于 METHOD | [https://doi.org/10.1214/aos/1013699998](https://doi.org/10.1214/aos/1013699998) |
| 5 | Intervention Analysis with Applications to Economic and Environmental Problems（Box, G. E. P.; Tiao, G. C.，1975，*Journal of the American Statistical Association*） | 方法 | 用于 METHOD | [https://doi.org/10.1080/01621459.1975.10480264](https://doi.org/10.1080/01621459.1975.10480264) |
| 6 | Bootstrap-Based Improvements for Inference with Clustered Errors（Cameron, A. C.; Gelbach, J. B.; Miller, D. L.，2008，*The Review of Economics and Statistics*） | 方法 | 用于 METHOD | [https://doi.org/10.1162/rest.90.3.414](https://doi.org/10.1162/rest.90.3.414) |
| 7 | Nonparametric Estimation from Incomplete Observations（Kaplan, E. L.; Meier, P.，1958，*Journal of the American Statistical Association*） | 方法 | 用于 METHOD | [https://doi.org/10.1080/01621459.1958.10501452](https://doi.org/10.1080/01621459.1958.10501452) |
| 8 | Event Studies in Economics and Finance（MacKinlay, A. C.，1997，*Journal of Economic Literature*） | 方法 | 用于 METHOD | [https://www.jstor.org/stable/2729691](https://www.jstor.org/stable/2729691) |
| 9 | A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix（Newey, W. K.; West, K. D.，1987，*Econometrica*） | 方法 | 用于 METHOD | [https://doi.org/10.2307/1913610](https://doi.org/10.2307/1913610) |
| 10 | Automatic Lag Selection in Covariance Matrix Estimation（Newey, W. K.; West, K. D.，1994，*The Review of Economic Studies*） | 方法 | 用于 METHOD | [https://doi.org/10.2307/2297912](https://doi.org/10.2307/2297912) |
| 11 | Fast and wild: Bootstrap inference in Stata using boottest（Roodman, D. et al.，2019，*The Stata Journal*） | 方法 | 用于 METHOD | [https://doi.org/10.1177/1536867X19830877](https://doi.org/10.1177/1536867X19830877) |
| 12 | Estimating dynamic treatment effects in event studies with heterogeneous treatment effects（Sun, L.; Abraham, S.，2021，*Journal of Econometrics*） | 方法 | 用于 METHOD | [https://doi.org/10.1016/j.jeconom.2020.09.006](https://doi.org/10.1016/j.jeconom.2020.09.006) |
| 13 | 我国蔬菜产业市场运行态势研究（安民; 曹姗姗; 孙伟; 孔汇鑫; 孔繁涛; 刘继芳，2024，*中国蔬菜*） | 学术 | 用于 A01 | [https://doi.org/10.19928/j.cnki.1000-6346.2024.1009](https://doi.org/10.19928/j.cnki.1000-6346.2024.1009) |
| 14 | Structural identification of weather impacts on crop yields: Disentangling agronomic from adaptation effects（Bareille, F.; Chakir, R.，2023，*American Journal of Agricultural Economics*） | 学术 | 用于 A08 | [https://doi.org/10.1111/ajae.12420](https://doi.org/10.1111/ajae.12420) |
| 15 | Heat, drought, and compound events: Thresholds and impacts on crop yield variability（Bogenreuther, J. et al.，2025，*Agricultural and Forest Meteorology*） | 学术 | 用于 A03/A08 | [https://doi.org/10.1016/j.agrformet.2025.110836](https://doi.org/10.1016/j.agrformet.2025.110836) |
| 16 | Weather and international price shocks on food prices in the developing world（Brown, M. E.; Kshirsagar, V.，2015，*Global Environmental Change*） | 学术 | 用于 A02/A04 | [https://doi.org/10.1016/j.gloenvcha.2015.08.003](https://doi.org/10.1016/j.gloenvcha.2015.08.003) |
| 17 | Global non-linear effect of temperature on economic production（Burke, M.; Hsiang, S. M.; Miguel, E.，2015，*Nature*） | 学术 | 用于 A03/A08 | [https://doi.org/10.1038/nature15725](https://doi.org/10.1038/nature15725) |
| 18 | Identifying the Economic Impacts of Climate Change on Agriculture（Carter, C. et al.，2018，*Annual Review of Resource Economics*） | 学术 | 用于 A08 | [https://doi.org/10.1146/annurev-resource-100517-022938](https://doi.org/10.1146/annurev-resource-100517-022938) |
| 19 | Response and adaptation of agriculture to climate change: Evidence from China（Chen, S.; Gong, B.，2021，*Journal of Development Economics*） | 学术 | 用于 A08 | [https://doi.org/10.1016/j.jdeveco.2020.102557](https://doi.org/10.1016/j.jdeveco.2020.102557) |
| 20 | The Economic Impacts of Climate Change: Evidence from Agricultural Output and Random Fluctuations in Weather（Deschênes, O.; Greenstone, M.，2007，*American Economic Review*） | 学术 | 用于 A08 | [https://doi.org/10.1257/aer.97.1.354](https://doi.org/10.1257/aer.97.1.354) |
| 21 | Food price seasonality in Africa: Measurement and extent（Gilbert, C. L.; Christiaensen, L.; Kaminski, J.，2017，*Food Policy*） | 学术 | 用于 A01 | [https://doi.org/10.1016/j.foodpol.2016.09.016](https://doi.org/10.1016/j.foodpol.2016.09.016) |
| 22 | The Impact of Extreme Weather Events on Global Soybean Markets and China's Imports（Hu, X. et al.，2025，*Journal of Agricultural Economics*） | 学术 | 用于 A04/A09 | [https://doi.org/10.1111/1477-9552.12632](https://doi.org/10.1111/1477-9552.12632) |
| 23 | How Aggregate Growing Season Temperature Metrics May Lead to Overestimation of the Effects of High Temperatures on Crop Yields: Evidence From China（Huang, K.; Zhang, P.，2026，*Journal of Agricultural Economics*） | 学术 | 用于 A08 | [https://doi.org/10.1111/1477-9552.70032](https://doi.org/10.1111/1477-9552.70032) |
| 24 | How Persistent are Climate-Related Price Shocks? Implications for Monetary Policy（Kabundi, A. N.; Mlachila, M.; Yao, J.，2022，*IMF Working Paper WP/22/207*） | 学术 | 用于 A03 | [https://www.elibrary.imf.org/view/journals/001/2022/207/article-A001-en.xml](https://www.elibrary.imf.org/view/journals/001/2022/207/article-A001-en.xml) |
| 25 | Climate extremes, food price spikes, and their wider societal risks（Kotz, M. et al.，2025，*Environmental Research Letters*） | 学术 | 用于 A04/A09 | [https://doi.org/10.1088/1748-9326/ade45f](https://doi.org/10.1088/1748-9326/ade45f) |
| 26 | Decompose food price disparities in China: Evidence from wholesale markets（Li, Q.; Yang, J.; Yang, X. et al.，2025，*Food Policy*） | 学术 | 用于 A06/A09 | [https://doi.org/10.1016/j.foodpol.2025.102817](https://doi.org/10.1016/j.foodpol.2025.102817) |
| 27 | The critical role of extreme heat for maize production in the United States（Lobell, D. B. et al.，2013，*Nature Climate Change*） | 学术 | 用于 A03/A08 | [https://doi.org/10.1038/nclimate1832](https://doi.org/10.1038/nclimate1832) |
| 28 | ARIMA model forecasting analysis of the prices of multiple vegetables under the impact of the COVID-19（Mao, L. et al.，2022，*PLoS ONE*） | 学术 | 用于 A01 | [https://doi.org/10.1371/journal.pone.0271594](https://doi.org/10.1371/journal.pone.0271594) |
| 29 | Price volatility transmission of perishable agricultural products: evidence from China（Pan, Z.; Zheng, X.，2023，*Economic Research-Ekonomska Istraživanja*） | 学术 | 用于 A06 | [https://doi.org/10.1080/1331677X.2023.2180058](https://doi.org/10.1080/1331677X.2023.2180058) |
| 30 | Climate change increases the interannual variance of summer crop yields globally（Proctor, J. et al.，2025，*Science Advances*） | 学术 | 用于 A08 | [https://doi.org/10.1126/sciadv.ady3575](https://doi.org/10.1126/sciadv.ady3575) |
| 31 | Identifying Supply and Demand Elasticities of Agricultural Commodities（Roberts, M. J.; Schlenker, W.，2013，*American Economic Review*） | 学术 | 用于 A06 | [https://doi.org/10.1257/aer.103.6.2265](https://doi.org/10.1257/aer.103.6.2265) |
| 32 | The Impact of Global Warming on U.S. Agriculture: An Econometric Analysis of Optimal Growing Conditions（Schlenker, W.; Hanemann, W. M.; Fisher, A. C.，2006，*The Review of Economics and Statistics*） | 学术 | 用于 A08 | [https://doi.org/10.1162/rest.2006.88.1.113](https://doi.org/10.1162/rest.2006.88.1.113) |
| 33 | Nonlinear temperature effects indicate severe damages to U.S. crop yields under climate change（Schlenker, W.; Roberts, M. J.，2009，*PNAS*） | 学术 | 用于 A03/A08 | [https://doi.org/10.1073/pnas.0906865106](https://doi.org/10.1073/pnas.0906865106) |
| 34 | Climate-crop yield relationships at provincial scales in China and the impacts of recent climate trends（Tao, F. et al.，2008，*Climate Research*） | 学术 | 用于 A08 | [https://doi.org/10.3354/cr00771](https://doi.org/10.3354/cr00771) |
| 35 | The Role of El Niño Southern Oscillation in Commodity Price Movement and Predictability（Ubilava, D.，2017，*American Journal of Agricultural Economics*） | 学术 | 用于 A02/A06 | [https://doi.org/10.1093/ajae/aax060](https://doi.org/10.1093/ajae/aax060) |
| 36 | Decoding the Temporal Effects of Climate Change on Crop Phenology: Cumulative and Lagged Impacts in China's Major Corn Zones（Yang, T. et al.，2026，*Earth's Future*） | 学术 | 用于 A03/A08 | [https://doi.org/10.1029/2025EF006965](https://doi.org/10.1029/2025EF006965) |
| 37 | 蔬菜价格短期波动传导机制分析——以上海青菜为例（杨娟; 钱婷婷; 郑秀国; 赵京音; 许叶颖，2020，*农业大数据学报*） | 学术 | 用于 A06 | [https://doi.org/10.19788/j.issn.2096-6369.200304](https://doi.org/10.19788/j.issn.2096-6369.200304) |
| 38 | 运输距离、中间环节与下游市场价格表现——基于对农产品流通特征的考察（张昊，2023，*财贸经济*） | 学术 | 用于 A06 | [https://cmjj.ajcass.com/Admin/Upload/FileDownload/?ContentID=89496](https://cmjj.ajcass.com/Admin/Upload/FileDownload/?ContentID=89496) |
| 39 | Short-term forecasting of vegetable prices based on LSTM model—Evidence from Beijing's vegetable data（Zhang, Q. et al.，2024，*PLoS ONE*） | 学术 | 用于 A01/A06 | [https://doi.org/10.1371/journal.pone.0304881](https://doi.org/10.1371/journal.pone.0304881) |
| 40 | The combined effects of VPD and soil moisture on historical maize yield and prediction in China（Zhao, F. et al.，2023，*Frontiers in Environmental Science*） | 学术 | 用于 A08 | [https://doi.org/10.3389/fenvs.2023.1117184](https://doi.org/10.3389/fenvs.2023.1117184) |
| 41 | Reinspecting the Climate-Crop Yields Relationship at a Finer Scale and the Climate Damage Evaluation: Evidence from China（Zhu, Y. et al.，2020，*Complexity*） | 学术 | 用于 A08 | [https://doi.org/10.1155/2020/9424327](https://doi.org/10.1155/2020/9424327) |
| 42 | The ERA5 global reanalysis（ERA5 数据集权威描述）（Hersbach, H. et al.，2020，*Quarterly Journal of the Royal Meteorological Society*） | 学术 | 引用 ERA5 变量与使用口径时的必备引证 | [https://doi.org/10.1002/qj.3803](https://doi.org/10.1002/qj.3803) |
| 43 | 2026 年 7 月沈阳/沈北强降雨灾情通报（市级/区级/街道级）（，2026-07，*沈阳市人民政府 / 沈北新区人民政府 / 辽宁省防汛抗旱指挥部*） | 学术 | 含市级平均降雨、转移人数、应急响应等级 | [https://www.shenyang.gov.cn/zwgk/zwdt/bmdt/](https://www.shenyang.gov.cn/zwgk/zwdt/bmdt/) |

## 三、来源分级说明

- **A**：政府统计部门 / 官方公报 / 国家级官方接口 / 同行评议文献
- **B**：区县本级政府门户 / 算法派生数据 / 区县年鉴（非市级统一口径）
- **C**：其他官方公开材料（本研究中未使用）
- **D**：非官方公开材料（本研究中未使用）

## 四、数据性质声明

1. 气象数据为 **ERA5 / ERA5-Land 再分析网格数据**，**不是气象站实测**；本系列全部文章均按此表述。
2. 批发市场**成交量单位官方未公开**（`volume_unit=unknown`）；全系列**禁止**把成交量写作「吨」，只使用 z / % / 相对口径。
3. 极端天气事件分**算法事件**（ERA5 阈值识别）与**官方事件**（政府/气象部门通报）两套，始终分开报告，不合并为一个概念。
4. 中国气象数据网（data.cma.cn）需实名认证，本项目**未绕过任何鉴权**，故改用公开再分析接口。

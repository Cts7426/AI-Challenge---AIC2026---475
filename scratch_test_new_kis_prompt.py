import json
from pathlib import Path
from backend.indexing.es_client import connect as es_connect
from backend.indexing.milvus_client import connect as milvus_connect
from backend.retrieval.search import search
from backend.slot.allocator import allocate
from dev_set.tools.run_evaluation import _to_shot_hits
from dev_set.tools.schema import GroundTruthKIS, Query
from dev_set.tools.scoring import final_score, recall_at_k, rscore_kis
from backend.indexing.frame_map import load_frame_map

RAW_DATA = """
{"query_id": "KIS_001_NEW", "query_vi": "Đoạn video ghi lại vụ va chạm xe cộ di chuyển giữa xe gắn máy và xe ba bánh trên đường phố, có người bị rơi xuống đường.", "query_en": "Video showing a traffic collision between a motorcycle and a three-wheeler on the street, someone fell on the street.", "type": "KIS", "video_id": "L21_V024", "frame_start": 13319, "frame_end": 13469, "best_frame_idx": 13394, "candidate_keyframes": ["L21_V024_0013394", "L21_V024_0013067", "L21_V024_0013310", "L21_V024_0013239", "L21_V024_0012888"], "candidate_frame_indices": [13394, 13067, 13310, 13239, 12888], "confidence": "auto_bm25"}
{"query_id": "KIS_002_NEW", "query_vi": "Một phương tiện tải chở hàng đang phát hỏa dữ dội khi chạy trên đường phố, khói đen bốc lên cao.", "query_en": "A vehiclego lorry was burning while driving on the street, black smoke rising high.", "type": "KIS", "video_id": "L22_V013", "frame_start": 27861, "frame_end": 28041, "best_frame_idx": 27951, "candidate_keyframes": ["L22_V013_0027951", "L22_V013_0028101", "L22_V013_0027368", "L22_V013_0029318", "L22_V013_0026950"], "candidate_frame_indices": [27951, 28101, 27368, 29318, 26950], "confidence": "auto_bm25"}
{"query_id": "KIS_003_NEW", "query_vi": "Khu vực vụ va chạm xe cộ di chuyển liên hoàn giữa ô tô tải và xe bán tải trên đường phố cao tốc dưới thời tiết mưa, gây ùn tắc kéo dài.", "query_en": "The video showing a traffic collision between a lorry and a pickup lorry on the freeway in the rainy weather, causing prolonged congestion.", "type": "KIS", "video_id": "L22_V012", "frame_start": 25173, "frame_end": 25353, "best_frame_idx": 25263, "candidate_keyframes": ["L22_V012_0025263", "L22_V012_0026492", "L22_V012_0025926", "L22_V012_0024591", "L22_V012_0024845"], "candidate_frame_indices": [25263, 26492, 25926, 24591, 24845], "confidence": "auto_bm25"}
{"query_id": "KIS_004_NEW", "query_vi": "Chi tiết: Cảnh một chiếc ô tô 7 chỗ bị biến dạng vỡ nát, nằm lăn lóc dưới ruộng lúa sau cú va chạm với xe ben.", "query_en": "Details: Video showing a deformed and broken 7-seater vehicle lying in the rice field after a collision with a dump lorry.", "type": "KIS", "video_id": "L21_V017", "frame_start": 13395, "frame_end": 13545, "best_frame_idx": 13470, "candidate_keyframes": ["L21_V017_0013470", "L21_V017_0013170", "L21_V017_0013345", "L21_V017_0013020", "L21_V017_0013560"], "candidate_frame_indices": [13470, 13170, 13345, 13020, 13560], "confidence": "auto_bm25"}
{"query_id": "KIS_005_NEW", "query_vi": "Khu vực vụ va chạm xe cộ di chuyển nghiêm trọng giữa một phương tiện container và xe gắn máy.", "query_en": "Video showing a serious traffic collision between a container lorry and a motorcycle.", "type": "KIS", "video_id": "L22_V031", "frame_start": 21190, "frame_end": 21340, "best_frame_idx": 21265, "candidate_keyframes": ["L22_V031_0021265", "L22_V031_0021300", "L22_V031_0021824", "L22_V031_0021870", "L22_V031_0028372"], "candidate_frame_indices": [21265, 21300, 21824, 21870, 28372], "confidence": "auto_bm25"}
{"query_id": "KIS_006_NEW", "query_vi": "Lực lượng cảnh sát đi trên xe xe phân khối lớn đặc chủng đang bật còi hú, mở đường cho một phương tiện taxi chạy phía sau.", "query_en": "Traffic officers riding on special motorcycles were turning on their sirens, opening the way for a taxi to drive behind.", "type": "KIS", "video_id": "L21_V023", "frame_start": 11624, "frame_end": 11804, "best_frame_idx": 11714, "candidate_keyframes": ["L21_V023_0011714", "L21_V023_0011750", "L21_V023_0012428", "L21_V023_0031140", "L21_V023_0031909"], "candidate_frame_indices": [11714, 11750, 12428, 31140, 31909], "confidence": "auto_bm25"}
{"query_id": "KIS_007_NEW", "query_vi": "Chi tiết: Hình ảnh xe cộ xếp hàng dài chờ đợi trên cầu Rạch Miễu trong đợt thử tải cầu.", "query_en": "Details: Image of vehicles waiting in long lines on Rach Mieu bridge during the bridge load test.", "type": "KIS", "video_id": "L21_V015", "frame_start": 1514, "frame_end": 1694, "best_frame_idx": 1604, "candidate_keyframes": ["L21_V015_0001604", "L21_V015_0001395", "L21_V015_0001732", "L21_V015_0002268", "L21_V015_0002023"], "candidate_frame_indices": [1604, 1395, 1732, 2268, 2023], "confidence": "auto_bm25"}
{"query_id": "KIS_008_NEW", "query_vi": "Khối lượng lớn bùn đất sạt lở tràn xuống lấp kín mặt đường đèo, các xe cộ xe cộ di chuyển bị ách tắc.", "query_en": "A large volume of mud and landslides submerged down and covered the pass road, causing traffic congestions.", "type": "KIS", "video_id": "L22_V027", "frame_start": 11256, "frame_end": 11436, "best_frame_idx": 11346, "candidate_keyframes": ["L22_V027_0011346", "L22_V027_0011483", "L22_V027_0011619", "L22_V027_0011778", "L22_V027_0011946"], "candidate_frame_indices": [11346, 11483, 11619, 11778, 11946], "confidence": "auto_bm25"}
{"query_id": "KIS_009_NEW", "query_vi": "Dòng người và xe gắn máy kẹt cứng, chen chúc nhau trên con đường cửa ngõ rời khỏi thành phố.", "query_en": "The flow of people and motorcycles was jammed, crowded together on the gateway road leaving the city.", "type": "KIS", "video_id": "L21_V031", "frame_start": 526, "frame_end": 676, "best_frame_idx": 601, "candidate_keyframes": ["L21_V031_0000601", "L21_V031_0000475", "L21_V031_0000293", "L21_V031_0000304", "L21_V031_0000347"], "candidate_frame_indices": [601, 475, 293, 304, 347], "confidence": "auto_bm25"}
{"query_id": "KIS_010_NEW", "query_vi": "Hình ảnh hàng dài xe gắn máy dừng chờ đèn đỏ tại một ngã tư sầm uất vào giờ tan tầm.", "query_en": "Image of a long line of motorcycles stopping at a red light at a busy intersection at rush hour.", "type": "KIS", "video_id": "L25_V048", "frame_start": 717, "frame_end": 895, "best_frame_idx": 806, "candidate_keyframes": ["L25_V048_0000806", "L25_V048_0000832", "L25_V048_0001236", "L25_V048_0001256", "L25_V048_0038282"], "candidate_frame_indices": [806, 832, 1236, 1256, 38282], "confidence": "auto_bm25"}
{"query_id": "KIS_011_NEW", "query_vi": "Phương tiện cẩu loại lớn đang kéo một xe cộ bị lật ngã ra khỏi khu vực.", "query_en": "A large hoist was pulling an overturned vehicle from the area.", "type": "KIS", "video_id": "L21_V012", "frame_start": 12002, "frame_end": 12182, "best_frame_idx": 12092, "candidate_keyframes": ["L21_V012_0012092", "L21_V012_0012212", "L21_V012_0014854", "L21_V012_0014740", "L21_V012_0011534"], "candidate_frame_indices": [12092, 12212, 14854, 14740, 11534], "confidence": "auto_bm25"}
{"query_id": "KIS_012_NEW", "query_vi": "Những lực lượng cứu hộ đang mặc áo phao hỗ trợ điều tiết xe cộ di chuyển trong vùng nước ngập sâu.", "query_en": "Rescue team are wearing life jackets to help regulate traffic in deeply submerged areas.", "type": "KIS", "video_id": "L24_V010", "frame_start": 1573, "frame_end": 1723, "best_frame_idx": 1648, "candidate_keyframes": ["L24_V010_0001648", "L24_V010_0001736", "L24_V010_0010788", "L24_V010_0003844", "L24_V010_0003968"], "candidate_frame_indices": [1648, 1736, 10788, 3844, 3968], "confidence": "auto_bm25"}
{"query_id": "KIS_013_NEW", "query_vi": "Một nam giới đi ngang qua đường không đúng nơi quy định suýt bị ô tô tải tông phải.", "query_en": "The male crossed the street at the wrong place and was almost struck by a lorry.", "type": "KIS", "video_id": "L26_V001", "frame_start": 1513, "frame_end": 1663, "best_frame_idx": 1588, "candidate_keyframes": ["L26_V001_0001588", "L26_V001_0001612", "L26_V001_0001635", "L26_V001_0001660", "L26_V001_0001684"], "candidate_frame_indices": [1588, 1612, 1635, 1660, 1684], "confidence": "auto_bm25"}
{"query_id": "KIS_014_NEW", "query_vi": "Những người phụ nữ trẻ trẻ bị xây xát nhẹ sau vụ ngã xe gắn máy trên đường phố.", "query_en": "The young young womales suffered minor injuries after falling off their motorcycle on the street.", "type": "KIS", "video_id": "L22_V010", "frame_start": 23687, "frame_end": 23837, "best_frame_idx": 23762, "candidate_keyframes": ["L22_V010_0023762", "L22_V010_0023788", "L22_V010_0023812", "L22_V010_0023836", "L22_V010_0023861"], "candidate_frame_indices": [23762, 23788, 23812, 23836, 23861], "confidence": "auto_bm25"}
{"query_id": "KIS_015_NEW", "query_vi": "Các vận động viên xe đạp thể thao đang tăng tốc độ rút đích ở những mét cuối cùng trên một đường thẳng rộng, đông đảo khán giả đứng hai bên.", "query_en": "The cyclists are speeding up to the end point in the final meters on a wide straight line, with a large crowd of spectators standing on both sides.", "type": "KIS", "video_id": "L23_V025", "frame_start": 4675, "frame_end": 4825, "best_frame_idx": 4750, "candidate_keyframes": ["L23_V025_0004750", "L23_V025_0006395", "L23_V025_0006500", "L23_V025_0005394", "L23_V025_0006970"], "candidate_frame_indices": [4750, 6395, 6500, 5394, 6970], "confidence": "auto_bm25"}
{"query_id": "KIS_016_NEW", "query_vi": "Nhóm đua xe đạp thể thao đang chạy dàn hàng ngang trên đường phố, các vận động viên ngoại binh bám sát nhau ở tốp đầu.", "query_en": "The bike racing group is running in a row on the street, the foreign riders sticking close to each other at the top.", "type": "KIS", "video_id": "L23_V005", "frame_start": 2427, "frame_end": 2577, "best_frame_idx": 2502, "candidate_keyframes": ["L23_V005_0002502", "L23_V005_0002233", "L23_V005_0002250", "L23_V005_0002364", "L23_V005_0002375"], "candidate_frame_indices": [2502, 2233, 2250, 2364, 2375], "confidence": "auto_bm25"}
{"query_id": "KIS_017_NEW", "query_vi": "Vận động viên Martin Lass tung nước rút mạnh mẽ vượt qua điểm chung cuộc, giương cao tay ăn mừng chiến thắng.", "query_en": "Athlete Martin Lass sprinted strongly across the end point, raising his arms high to celebrate victory.", "type": "KIS", "video_id": "L23_V013", "frame_start": 0, "frame_end": 75, "best_frame_idx": 0, "candidate_keyframes": ["L23_V013_0000000", "L23_V013_0000117", "L23_V013_0000217", "L23_V013_0005161", "L23_V013_0005336"], "candidate_frame_indices": [0, 117, 217, 5161, 5336], "confidence": "auto_bm25"}
{"query_id": "KIS_018_NEW", "query_vi": "Hình ảnh chậm tại điểm chung cuộc, bánh xe của hai vận động viên xe đạp thể thao gần như chạm vạch cùng một lúc.", "query_en": "Slow motion area at the end point, two cyclists' wheels almost touching the line at the same time.", "type": "KIS", "video_id": "L23_V022", "frame_start": 8050, "frame_end": 8200, "best_frame_idx": 8125, "candidate_keyframes": ["L23_V022_0008125", "L23_V022_0007773", "L23_V022_0007875", "L23_V022_0007950", "L23_V022_0007598"], "candidate_frame_indices": [8125, 7773, 7875, 7950, 7598], "confidence": "auto_bm25"}
{"query_id": "KIS_019_NEW", "query_vi": "Ba vận động viên xe đạp thể thao đang bứt phá đi đầu, phía sau họ là đoàn đông bị bỏ lại khá xa.", "query_en": "Three cyclists were taking the lead, behind them was a large group that was left far behind.", "type": "KIS", "video_id": "L23_V012", "frame_start": 7313, "frame_end": 7463, "best_frame_idx": 7388, "candidate_keyframes": ["L23_V012_0007388", "L23_V012_0007425", "L23_V012_0007875", "L23_V012_0004517", "L23_V012_0004582"], "candidate_frame_indices": [7388, 7425, 7875, 4517, 4582], "confidence": "auto_bm25"}
{"query_id": "KIS_020_NEW", "query_vi": "Một tốp vận động viên xe đạp thể thao đang cạnh tranh gay gắt ở vạch mức giải thưởng dọc đường.", "query_en": "A group of cyclists are competing fiercely at the prize line along the road.", "type": "KIS", "video_id": "L23_V021", "frame_start": 9419, "frame_end": 9569, "best_frame_idx": 9494, "candidate_keyframes": ["L23_V021_0009494", "L23_V021_0009668", "L23_V021_0009419", "L23_V021_0009274", "L23_V021_0009779"], "candidate_frame_indices": [9494, 9668, 9419, 9274, 9779], "confidence": "auto_bm25"}
{"query_id": "KIS_021_NEW", "query_vi": "Hai vận động viên đi cạnh nhau liên tục canh chừng đối phương ở đoạn đường trống trải.", "query_en": "Two riders walking side by side constantly watch out for each other on the open road.", "type": "KIS", "video_id": "L23_V017", "frame_start": 580, "frame_end": 730, "best_frame_idx": 655, "candidate_keyframes": ["L23_V017_0000655", "L23_V017_0001065", "L23_V017_0001108", "L23_V017_0002402", "L23_V017_0000780"], "candidate_frame_indices": [655, 1065, 1108, 2402, 780], "confidence": "auto_bm25"}
{"query_id": "KIS_022_NEW", "query_vi": "Góc quay từ phía trước nhìn thấy rõ nét căng thẳng trên khuôn mặt các vận động viên đang dồn sức tung nước rút.", "query_en": "The camera angle from the front clearly shows the tension on the faces of the riders who are focusing their strength on the sprint.", "type": "KIS", "video_id": "L23_V010", "frame_start": 2244, "frame_end": 2394, "best_frame_idx": 2319, "candidate_keyframes": ["L23_V010_0002319", "L23_V010_0002250", "L23_V010_0001750", "L23_V010_0000625", "L23_V010_0002750"], "candidate_frame_indices": [2319, 2250, 1750, 625, 2750], "confidence": "auto_bm25"}
{"query_id": "KIS_023_NEW", "query_vi": "Con chó Labrador màu nâu đang đứng thăng bằng trên ván lướt sóng cùng chủ nhân giữa biển.", "query_en": "A brown Labrador canine is balancing on a surfboard with its owner in the middle of the ocean.", "type": "KIS", "video_id": "L22_V005", "frame_start": 27815, "frame_end": 27995, "best_frame_idx": 27905, "candidate_keyframes": ["L22_V005_0027905", "L22_V005_0028107", "L22_V005_0028686", "L22_V005_0028197", "L22_V005_0028343"], "candidate_frame_indices": [27905, 28107, 28686, 28197, 28343], "confidence": "auto_bm25"}
{"query_id": "KIS_024_NEW", "query_vi": "Tốp đông vận động viên xe đạp thể thao đang cạnh tranh nước rút ở những mét cuối tại một giải đua quốc tế ở Tây Ban Nha.", "query_en": "A large group of cyclists are competing in a sprint in the final meters at an international race in Spain.", "type": "KIS", "video_id": "L21_V029", "frame_start": 29696, "frame_end": 29876, "best_frame_idx": 29786, "candidate_keyframes": ["L21_V029_0029786", "L21_V029_0030526", "L21_V029_0030443", "L21_V029_0030156", "L21_V029_0030359"], "candidate_frame_indices": [29786, 30526, 30443, 30156, 30359], "confidence": "auto_bm25"}
{"query_id": "KIS_025_NEW", "query_vi": "Những vận động viên ăn mừng trên bục nhận giải, mặc áo vàng chung cuộc.", "query_en": "The riders celebrate on the podium, wearing yellow final jerseys.", "type": "KIS", "video_id": "L26_V002", "frame_start": 916, "frame_end": 1066, "best_frame_idx": 991, "candidate_keyframes": ["L26_V002_0000991", "L26_V002_0001016", "L26_V002_0001041", "L26_V002_0001067", "L26_V002_0001092"], "candidate_frame_indices": [991, 1016, 1041, 1067, 1092], "confidence": "auto_bm25"}
{"query_id": "KIS_026_NEW", "query_vi": "Đội đua xe đạp thể thao Đồng Tháp dang xếp thành đội hình hàng dọc để núp gió.", "query_en": "The Dong Thap cycling team is lining up in a vertical line to hide from the wind.", "type": "KIS", "video_id": "L25_V001", "frame_start": 19205, "frame_end": 19355, "best_frame_idx": 19280, "candidate_keyframes": ["L25_V001_0019280", "L25_V001_0019308", "L25_V001_0019335", "L25_V001_0019362", "L25_V001_0019390"], "candidate_frame_indices": [19280, 19308, 19335, 19362, 19390], "confidence": "auto_bm25"}
{"query_id": "KIS_027_NEW", "query_vi": "Xe xe phân khối lớn của ban tổ chức chạy sát theo đoàn đua để thông báo khoảng cách.", "query_en": "The organizers' motorcycles followed the race group to announce the distance.", "type": "KIS", "video_id": "L24_V012", "frame_start": 2342, "frame_end": 2428, "best_frame_idx": 2417, "candidate_keyframes": ["L24_V012_0002417", "L24_V012_0002424", "L24_V012_0001495", "L24_V012_0001536", "L24_V012_0001090"], "candidate_frame_indices": [2417, 2424, 1495, 1536, 1090], "confidence": "auto_bm25"}
{"query_id": "KIS_029_NEW", "query_vi": "Chi tiết: Một con bò đang đứng ở bãi cỏ", "query_en": "Details: A cow is standing in the grass", "type": "KIS", "video_id": "L21_V001", "frame_start": 20069, "frame_end": 20249, "best_frame_idx": 20159, "candidate_keyframes": ["L21_V001_0020159", "L21_V001_0020189", "L21_V001_0020219", "L21_V001_0020249", "L21_V001_0020278"], "candidate_frame_indices": [20159, 20189, 20219, 20249, 20278], "confidence": "auto_bm25"}
{"query_id": "KIS_030_NEW", "query_vi": "Người phụ nữ trẻ mặc áo màu hồng đang đứng nói chuyện", "query_en": "The young womale wearing a pink shirt is standing and talking", "type": "KIS", "video_id": "L21_V001", "frame_start": 17408, "frame_end": 17588, "best_frame_idx": 17498, "candidate_keyframes": ["L21_V001_0017498", "L21_V001_0017530", "L21_V001_0017563", "L21_V001_0017596", "L21_V001_0017627"], "candidate_frame_indices": [17498, 17530, 17563, 17596, 17627], "confidence": "auto_bm25"}
{"query_id": "KIS_031_NEW", "query_vi": "Hình ảnh của máy bay trên không", "query_en": "Aerial footage of planes", "type": "KIS", "video_id": "L21_V003", "frame_start": 27195, "frame_end": 27345, "best_frame_idx": 27270, "candidate_keyframes": ["L21_V003_0027270", "L21_V003_0006812", "L21_V003_0006838", "L21_V003_0006864", "L21_V003_0006889"], "candidate_frame_indices": [27270, 6812, 6838, 6864, 6889], "confidence": "auto_bm25"}
{"query_id": "KIS_033_NEW", "query_vi": "Lực lượng cảnh sát đang làm việc với tài xế", "query_en": "Traffic officers are working with the driver", "type": "KIS", "video_id": "L21_V005", "frame_start": 27014, "frame_end": 27194, "best_frame_idx": 27104, "candidate_keyframes": ["L21_V005_0027104", "L21_V005_0027054", "L21_V005_0026679", "L21_V005_0027185", "L21_V005_0026938"], "candidate_frame_indices": [27104, 27054, 26679, 27185, 26938], "confidence": "auto_bm25"}
{"query_id": "KIS_034_NEW", "query_vi": "Chi tiết: Ngôi nhà bị cháy rụi", "query_en": "Details: The house burned down", "type": "KIS", "video_id": "L21_V006", "frame_start": 13233, "frame_end": 13413, "best_frame_idx": 13323, "candidate_keyframes": ["L21_V006_0013323", "L21_V006_0014043", "L21_V006_0013683", "L21_V006_0013893", "L21_V006_0013527"], "candidate_frame_indices": [13323, 14043, 13683, 13893, 13527], "confidence": "auto_bm25"}
{"query_id": "KIS_035_NEW", "query_vi": "Chi tiết: Người phụ nữ đứng nấu ăn trong bếp", "query_en": "Details: Womale standing in the kitchen cooking", "type": "KIS", "video_id": "L21_V007", "frame_start": 4922, "frame_end": 5102, "best_frame_idx": 5012, "candidate_keyframes": ["L21_V007_0005012", "L21_V007_0004874", "L21_V007_0005688", "L21_V007_0004232", "L21_V007_0009999"], "candidate_frame_indices": [5012, 4874, 5688, 4232, 9999], "confidence": "auto_bm25"}
{"query_id": "KIS_036_NEW", "query_vi": "Chi tiết: Xe cứu hỏa đang phun nước", "query_en": "Details: The fire lorry is spraying water", "type": "KIS", "video_id": "L21_V008", "frame_start": 13725, "frame_end": 13875, "best_frame_idx": 13800, "candidate_keyframes": ["L21_V008_0013800", "L21_V008_0013950", "L21_V008_0014191", "L21_V008_0014100", "L21_V008_0014340"], "candidate_frame_indices": [13800, 13950, 14191, 14100, 14340], "confidence": "auto_bm25"}
{"query_id": "KIS_037_NEW", "query_vi": "Va chạm xe cộ di chuyển giữa 2 xe gắn máy", "query_en": "Traffic collision between 2 motorcycles", "type": "KIS", "video_id": "L21_V009", "frame_start": 12075, "frame_end": 12225, "best_frame_idx": 12150, "candidate_keyframes": ["L21_V009_0012150", "L21_V009_0011997", "L21_V009_0021720", "L21_V009_0025650", "L21_V009_0021628"], "candidate_frame_indices": [12150, 11997, 21720, 25650, 21628], "confidence": "auto_bm25"}
{"query_id": "KIS_038_NEW", "query_vi": "Chi tiết: Những đứa trẻ đang chơi trong công viên", "query_en": "Details: The children are playing in the park", "type": "KIS", "video_id": "L21_V010", "frame_start": 17342, "frame_end": 17492, "best_frame_idx": 17417, "candidate_keyframes": ["L21_V010_0017417", "L21_V010_0016850", "L21_V010_0008232", "L21_V010_0008100", "L21_V010_0008212"], "candidate_frame_indices": [17417, 16850, 8232, 8100, 8212], "confidence": "auto_bm25"}
"""

def main():
    print("Connecting to DB...")
    es_connect()
    milvus_connect()
    fmap = load_frame_map()
    
    rows = []
    for line in RAW_DATA.strip().split('\n'):
        if not line.strip(): continue
        try:
            data = json.loads(line.strip())
        except Exception as e:
            continue
            
        if "KIS" in data.get("type", "") and data.get("query_id", "").endswith("_NEW"):
            try:
                if data.get("frame_start") is None or data.get("frame_end") is None:
                    continue
                q = Query(
                    query_id=data["query_id"],
                    task_type="KIS",
                    query_vi=data["query_vi"],
                    query_en=data.get("query_en"),
                    split="tune"
                )
                gt = GroundTruthKIS(
                    query_id=data["query_id"],
                    video_id=data["video_id"],
                    frame_start=data["frame_start"],
                    frame_end=data["frame_end"]
                )
                
                res = search(q.query_vi, q.query_en, top_k=100, group_by_shot=True)
                hits = _to_shot_hits(res)
                ans = allocate(hits, "KIS", answer_text=None)
                
                r1 = recall_at_k(ans, gt, "KIS", 1)
                r5 = recall_at_k(ans, gt, "KIS", 5)
                r20 = recall_at_k(ans, gt, "KIS", 20)
                r50 = recall_at_k(ans, gt, "KIS", 50)
                r100 = recall_at_k(ans, gt, "KIS", 100)
                fin = final_score(ans, gt, "KIS")
                
                raw_rank = None
                for i, row in enumerate(res, 1):
                    kf = row.get("keyframe_id")
                    if kf not in fmap:
                        continue
                    if rscore_kis(row["video_id"], fmap[kf], gt) > 0:
                        raw_rank = i
                        break

                rows.append({
                    "id": q.query_id,
                    "fin": fin,
                    "r1": r1, "r5": r5, "r20": r20, "r50": r50, "r100": r100,
                    "raw": raw_rank,
                    "vi": q.query_vi[:60]
                })
                print(f"{q.query_id} -> fin={fin:.3f} (raw={raw_rank})")
            except Exception as e:
                print("Err on", data.get("query_id"), ":", e)

    print("\n=== RESULTS ===")
    if not rows:
        print("No valid NEW KIS queries found.")
        return
        
    for r in rows:
        tick = "✅" if r["r1"] >= 1.0 else ("🟡" if r["r100"] >= 1.0 else "❌")
        print(f" {tick} {r['id']:15s} R@1={r['r1']:.2f} R@5={r['r5']:.2f} R@20={r['r20']:.2f} R@100={r['r100']:.2f} Final={r['fin']:.3f} (raw={r['raw']})")
        
    n = len(rows)
    avg = lambda k: sum(r[k] for r in rows) / n
    print(f"\nAvg Final Score ({n} q): {avg('fin'):.3f}")

if __name__ == "__main__":
    main()

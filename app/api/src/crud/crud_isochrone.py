import io
import os
import shutil
import uuid
from datetime import datetime
from json import loads
from random import randint
from turtle import speed
from typing import Any

import pandas as pd
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from geojson import FeatureCollection
from geopandas import GeoDataFrame, GeoSeries
from geopandas.io.sql import read_postgis
from pandas.io.sql import read_sql
from pyproj import Transformer, transform
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio.session import AsyncSession
from sqlalchemy.sql import text

from src.crud.base import CRUDBase
from src.db import models
from src.db.session import legacy_engine
from src.exts.cpp.bind import isochrone as isochrone_cpp
from src.resources.enums import SQLReturnTypes, IsochroneExportType
from src.schemas.isochrone import (
    IsochroneExport,
    IsochroneMulti,
    IsochroneMultiCountPois,
    IsochronePoiMulti,
    IsochroneSingle,
    IsochroneTypeEnum,
    IsochronePoiMulti,
)
from src.crud.base import CRUDBase
from fastapi import HTTPException
from src.utils import delete_dir


class CRUDIsochroneCalculation(
    CRUDBase[models.IsochroneCalculation, models.IsochroneCalculation, models.IsochroneCalculation]
):
    pass


isochrone_calculation = CRUDIsochroneCalculation(models.IsochroneCalculation)


class CRUDIsochroneFeature(
    CRUDBase[models.IsochroneFeature, models.IsochroneFeature, models.IsochroneFeature]
):
    pass


isochrone_feature = CRUDIsochroneCalculation(models.IsochroneFeature)


class CRUDIsochrone:
    async def read_network(self, db, calculation_type, obj_in, obj_in_data):

        if calculation_type == IsochroneTypeEnum.single:
            sql_text = f"""SELECT id, source, target, cost, reverse_cost, coordinates_3857 as geom, length_3857 AS length, starting_ids, starting_geoms
            FROM basic.fetch_network_routing(ARRAY[:x],ARRAY[:y], :max_cutoff, :speed, :modus, :scenario_id, :routing_profile)
            """
        elif calculation_type == IsochroneTypeEnum.multi:
            sql_text = f"""SELECT id, source, target, cost, reverse_cost, coordinates_3857 as geom, length_3857 AS length, starting_ids, starting_geoms
            FROM basic.fetch_network_routing_multi(:x,:y, :max_cutoff, :speed, :modus, :scenario_id, :routing_profile)
            """
        else:
            raise Exception("Unknown calculation type")

        read_network_sql = text(sql_text)

        edges_network = read_sql(read_network_sql, legacy_engine, params=obj_in_data)
        starting_id = edges_network.iloc[0].starting_ids

        # There was an issue when removing the first row (which only contains the starting point) from the edges. So it was kept.
        distance_limits = list(
            range(
                obj_in.max_cutoff // obj_in.n, obj_in.max_cutoff + 1, obj_in.max_cutoff // obj_in.n
            )
        )

        if calculation_type == IsochroneTypeEnum.single:
            starting_point_geom = str(
                GeoDataFrame(
                    {"geometry": Point(edges_network.iloc[-1:]["geom"].values[0][0])},
                    crs="EPSG:3857",
                    index=[0],
                )
                .to_crs("EPSG:4326")
                .to_wkt()["geometry"]
                .iloc[0]
            )
        elif calculation_type == IsochroneTypeEnum.multi:
            starting_point_geom = str(edges_network["starting_geoms"].iloc[0])

        edges_network = edges_network.drop(["starting_ids", "starting_geoms"], axis=1)

        obj_starting_point = models.IsochroneCalculation(
            calculation_type=calculation_type,
            user_id=obj_in.user_id,
            scenario_id=None if obj_in.scenario_id == 0 else obj_in.scenario_id,
            starting_point=starting_point_geom,
            routing_profile=obj_in.routing_profile,
            speed=obj_in.speed,
            modus=obj_in.modus,
            parent_id=None,
        )

        db.add(obj_starting_point)
        await db.commit()
        await db.refresh(obj_starting_point)

        return edges_network, starting_id, distance_limits, obj_starting_point

    def result_to_gdf(self, result, starting_id):
        isochrones = {}
        for isochrone_result in result.isochrone:
            for step in sorted(isochrone_result.shape):
                if list(isochrones.keys()) == []:
                    isochrones[step] = GeoSeries(Polygon(isochrone_result.shape[step]))
                else:
                    isochrones[step] = GeoSeries(
                        isochrones[previous_step].union(Polygon(isochrone_result.shape[step]))
                    )
                previous_step = step

        isochrones_multipolygon = {}
        for step in isochrones.keys():
            if isochrones[step][0].geom_type == "Polygon":
                isochrones_multipolygon[step] = MultiPolygon([isochrones[step][0]])
            elif isochrones[step][0].geom_type == "MultiPolygon":
                isochrones_multipolygon[step] = MultiPolygon(isochrones[step][0])
            else:
                raise Exception("Not correct geom type")

        isochrone_gdf = GeoDataFrame(
            {
                "step": list(isochrones_multipolygon.keys()),
                "geometry": GeoSeries(isochrones_multipolygon.values()).set_crs("EPSG:3857"),
                "isochrone_calculation_id": [starting_id] * len(isochrones),
            }
        ).to_crs("EPSG:4326")

        isochrone_gdf.rename_geometry("geom", inplace=True)
        isochrone_gdf.to_postgis(
            name="isochrone_feature", con=legacy_engine, schema="customer", if_exists="append"
        )
        return isochrone_gdf

    async def compute_isochrone(self, db: AsyncSession, *, obj_in, return_network=False):
        obj_in_data = jsonable_encoder(obj_in)
        edges_network, starting_id, distance_limits, obj_starting_point = await self.read_network(
            db, IsochroneTypeEnum.single.value, obj_in, obj_in_data
        )

        obj_in_data["starting_point_id"] = obj_starting_point.id

        # Convert the isochrones result to a geodataframe and save isochrone_feature to postgis
        result = isochrone_cpp(edges_network, starting_id, distance_limits)
        isochrone_gdf = self.result_to_gdf(result, obj_starting_point.id)

        # Compute reached opportunities
        sql = text(
            """SELECT * FROM basic.thematic_data_sum(:user_id,:starting_point_id,:modus,:scenario_id,:active_upload_ids) ORDER BY isochrone_feature_step"""
        )
        result_opportunities = await db.execute(sql, obj_in_data)
        result_opportunities = result_opportunities.all()
        dict_opportunities = {}
        [dict_opportunities.update({row[1]: row[2]}) for row in result_opportunities]
        dict_ids = {}
        [dict_ids.update({row[1]: row[0]}) for row in result_opportunities]
        await db.commit()

        # Update isochrones with reached opportunities
        isochrone_gdf["id"] = isochrone_gdf["step"].map(dict_ids)
        isochrone_gdf["reached_opportunities"] = isochrone_gdf["step"].map(dict_opportunities)
        isochrone_gdf["routing_profile"] = obj_in.routing_profile
        isochrone_gdf["scenario_id"] = obj_in.scenario_id
        isochrone_gdf["modus"] = obj_in.modus

        return_obj = {"isochrones": isochrone_gdf}

        if return_network == True:
            features = []
            transformer = Transformer.from_crs(3857, 4326, always_xy=True)
            for edge in result.network:
                coords = []
                for i in edge.shape:
                    coords.append(transformer.transform(i[0], i[1]))
                feature = {
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "type": "Feature",
                    "properties": {
                        "edge_id": edge.edge,
                        "isochrone_calculation_id": obj_starting_point.id,
                        "cost": max(edge.start_cost, edge.end_cost),
                        "start_cost": edge.start_cost,
                        "end_cost": edge.end_cost,
                        "start_perc": edge.start_perc,
                        "end_perc": edge.end_perc,
                        "routing_profile": obj_in.routing_profile,
                        "scenario_id": obj_in.scenario_id,
                        "modus": obj_in.modus,
                    },
                }
                features.append(feature)

            network_feature_collection = {"type": "FeatureCollection", "features": features}

            return_obj["network"] = network_feature_collection

        return return_obj

    async def compute_multi_isochrone(
        self, db: AsyncSession, *, obj_in, return_network=False
    ) -> GeoDataFrame:
        obj_in_data = jsonable_encoder(obj_in)
        edges_network, starting_id, distance_limits, obj_starting_point = await self.read_network(
            db, IsochroneTypeEnum.multi.value, obj_in, obj_in_data
        )
        obj_in_data["starting_point_id"] = starting_id

        result = isochrone_cpp(edges_network, starting_id, distance_limits)
        isochrone_gdf = self.result_to_gdf(result, obj_starting_point.id)

        return isochrone_gdf

    async def calculate_single_isochrone(self, db: AsyncSession, *, obj_in) -> GeoDataFrame:

        obj_in.speed = obj_in.speed / 3.6
        if obj_in.modus == "default" or obj_in.modus == "scenario":
            result = await self.compute_isochrone(db, obj_in=obj_in, return_network=False)
            result = result["isochrones"]
        elif obj_in.modus == "comparison":
            # Compute default isochrones
            obj_in_default = obj_in
            obj_in_default.modus = "default"
            isochrones_default = await self.compute_isochrone(
                db, obj_in=obj_in_default, return_network=False
            )
            # Compute scenario isochrones
            obj_in_scenario = obj_in
            obj_in_scenario.modus = "scenario"
            isochrones_scenario = await self.compute_isochrone(
                db, obj_in=obj_in_scenario, return_network=False
            )

            # Merge default and scenario isochrones
            result = GeoDataFrame(
                pd.concat([isochrones_default["isochrones"], isochrones_scenario["isochrones"]])
            )
        return result.reset_index(drop=True)

    async def calculate_reached_network(
        self, db: AsyncSession, *, obj_in: IsochroneSingle
    ) -> FeatureCollection:
        obj_in.speed = obj_in.speed / 3.6
        result = await self.compute_isochrone(db, obj_in=obj_in, return_network=True)
        result = result["network"]

        return result

    async def calculate_multi_isochrones(self, db: AsyncSession, *, obj_in) -> GeoDataFrame:

        obj_in.speed = obj_in.speed / 3.6
        await self.compute_multi_isochrone(db, obj_in=obj_in, return_network=False)

        if obj_in.modus == "default" or obj_in.modus == "scenario":
            result = await self.compute_multi_isochrone(db, obj_in=obj_in, return_network=False)
        elif obj_in.modus == "comparison":
            # Compute default isochrones
            obj_in_default = obj_in
            obj_in_default.modus = "default"
            isochrones_default = await self.compute_multi_isochrone(
                db, obj_in=obj_in, return_network=False
            )

            # Compute scenario isochrones
            obj_in_scenario = obj_in
            obj_in_scenario.modus = "scenario"
            isochrones_scenario = await self.compute_multi_isochrone(
                db, obj_in=obj_in, return_network=False
            )

            # Merge default and scenario isochrones
            result = GeoDataFrame(pd.concat([isochrones_default, isochrones_scenario]))
        return result.reset_index(drop=True)

    async def count_pois_multi_isochrones(self, db: AsyncSession, *, obj_in) -> dict:
        obj_in_data = jsonable_encoder(obj_in)
        sql = text(
            """SELECT count_pois
            FROM basic.count_pois_multi_isochrones(:user_id,:modus,:minutes,:speed,:region_type,:region,:amenities,:scenario_id,:active_upload_ids)"""
        )
        result = await db.execute(sql, obj_in_data)
        return result.fetchall()[0][0]

    async def calculate_pois_multi_isochrones(self, db: AsyncSession, *, obj_in) -> GeoDataFrame:
        obj_in.speed = obj_in.speed / 3.6
        obj_in_data = jsonable_encoder(obj_in)

        # Get starting points for multi-isochrone
        sql_starting_points = text(
            """SELECT x, y 
        FROM basic.starting_points_multi_isochrones(:modus, :minutes, :speed, :amenities, :scenario_id, :active_upload_ids, :region_geom, :study_area_ids)"""
        )
        starting_points = await db.execute(sql_starting_points, obj_in_data)
        starting_points = starting_points.fetchall()
        obj_in_data["x"] = starting_points[0][0]
        obj_in_data["y"] = starting_points[0][1]

        obj_multi_isochrones = IsochroneMulti(
            user_id=obj_in.user_id,
            scenario_id=obj_in.scenario_id,
            speed=obj_in.speed,
            modus=obj_in.modus,
            n=obj_in.n,
            minutes=obj_in.minutes,
            routing_profile=obj_in.routing_profile,
            active_upload_ids=obj_in.active_upload_ids,
            x=obj_in_data["x"],
            y=obj_in_data["y"],
        )

        # Compute Multi-Isochrones
        isochrones_result = await self.compute_multi_isochrone(
            db, obj_in=obj_multi_isochrones, return_network=False
        )
        isochrone_calculation_id = isochrones_result.isochrone_calculation_id.iloc[0]

        # Compute reached population
        if obj_in.region_type == "study_area":
            obj_population_multi_isochrones = {
                "isochrone_calculation_id": isochrone_calculation_id,
                "scenario_id": obj_in.scenario_id,
                "modus": obj_in.modus,
                "study_area_ids": obj_in.study_area_ids,
            }
            sql_reached_population = text(
                """SELECT * 
            FROM basic.reached_population_study_area(:isochrone_calculation_id, :scenario_id, :modus, :study_area_ids)
            """
            )
        else:
            obj_population_multi_isochrones = {
                "isochrone_calculation_id": isochrone_calculation_id,
                "scenario_id": obj_in.scenario_id,
                "modus": obj_in.modus,
                "region": obj_in.region[0],
            }
            sql_reached_population = text(
                """SELECT * 
            FROM basic.reached_population_polygon(:isochrone_calculation_id, :scenario_id, :modus, :region)
            """
            )

        result_reached_population = await db.execute(
            sql_reached_population, obj_population_multi_isochrones
        )
        await db.commit()

        dict_opportunities = {}
        [
            dict_opportunities.update({row[1]: row[2]})
            for row in result_reached_population.fetchall()
        ]
        isochrones_result["reached_opportunities"] = isochrones_result["step"].map(
            dict_opportunities
        )
        isochrones_result["routing_profile"] = obj_in.routing_profile
        isochrones_result["scenario_id"] = obj_in.scenario_id
        isochrones_result["modus"] = obj_in.modus

        return isochrones_result

    async def export_isochrone(
        self, db: AsyncSession, *, current_user, isochrone_calculation_id, return_type
    ) -> Any:

        sql = text(
            """
            SELECT f.isochrone_calculation_id, f.id, c.modus, c.routing_profile, f.step AS seconds, f.reached_opportunities, f.geom, c.creation_date::text 
            FROM customer.isochrone_calculation c, customer.isochrone_feature f
            WHERE c.id = f.isochrone_calculation_id
            AND c.id = :isochrone_calculation_id
            AND c.user_id = :user_id
            """
        )

        gdf = read_postgis(
            sql,
            legacy_engine,
            geom_col="geom",
            params={
                "user_id": current_user.id,
                "isochrone_calculation_id": isochrone_calculation_id,
            },
        )
        gdf = pd.concat([gdf, pd.json_normalize(gdf["reached_opportunities"])], axis=1, join="inner")
        defined_uuid = uuid.uuid4().hex
        file_name = "isochrone_export"
        file_dir = f"/tmp/{defined_uuid}"

        os.makedirs(file_dir+"/export")
        os.chdir(file_dir+"/export")

        if return_type == "geojson" or return_type == 'shp':
            gdf.to_file(file_name + '.' + return_type, driver=IsochroneExportType[return_type].value)
        elif return_type == "xlsx":
            gdf = gdf.drop(["reached_opportunities", "geom"], axis=1)
            gdf.transpose().to_excel(file_name + '.' + return_type)

        os.chdir(file_dir)
        shutil.make_archive(file_name, "zip", file_dir+"/export")

        with open(file_name + '.zip', "rb") as f:
            data = f.read()
        
        delete_dir(file_dir)
        response = StreamingResponse(io.BytesIO(data), media_type="application/zip")
        response.headers["Content-Disposition"] = "attachment; filename={}".format(file_name + '.zip')
        return response


isochrone = CRUDIsochrone()


#     edge_obj = {

#     }
#     full_edge_objs.append(edge_obj)

#     if edge.start_perc not in [0.0, 1.0] or edge.end_perc not in [0.0, 1.0] or edge.edge in [999999999,999999998]:
#         edge_obj["partial_edge"] = True
#         edge_obj["geom"] = 'Linestring(%s)' % re.sub(',([^,]*,?)', r'\1', str(edge.shape)).replace('[', '').replace(']', '')
#         partial_edge_objs.append(edge_obj)


# await db.execute(IsochroneEdgeDB.__table__.insert(), full_edge_objs)
# await db.execute(IsochroneEdgeDB.__table__.insert(), partial_edge_objs)
# await db.commit()

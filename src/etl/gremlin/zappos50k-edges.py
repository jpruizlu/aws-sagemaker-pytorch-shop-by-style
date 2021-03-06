import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as f
from pyspark.sql.functions import udf
from pyspark.sql import types as t
from pyspark.sql.functions import monotonically_increasing_id
from pyspark.sql.functions import lit

args = getResolvedOptions(sys.argv, ['JOB_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

similarity_tuples = glueContext.create_dynamic_frame.from_catalog(database="zappos-prod-similarity", table_name="out")

verticesDF = glueContext.create_dynamic_frame.from_catalog(database="zappos-prod-similarity", table_name="vertices").toDF()
analyzed_products = similarity_tuples.toDF().groupby(['category','subcategory','brand','productid']).agg(f.count(f.col('productid')).alias('c'))

vertices_to_process = analyzed_products \
.join(verticesDF.alias('v'), (f.col('v.category:string') == f.col('category')) \
& (f.col('v.subcategory:string') == f.col('subcategory')) \
& (f.col('v.brand:string') == f.col('brand')) \
& (f.col('v.product:string') == f.col('productid'))) \
.select(f.col('v.~id'), f.col('category'), f.col('subcategory'), f.col('brand'), f.col('productid'))

edgesDF= similarity_tuples.toDF().alias('st') \
.join(vertices_to_process.alias('vtp'), (f.col('vtp.category') == f.col('st.category')) \
& (f.col('vtp.subcategory') == f.col('st.subcategory')) \
& (f.col('vtp.brand') == f.col('st.brand')) \
& (f.col('vtp.productid') == f.col('st.productid'))) \
.join(verticesDF.alias('v'), (f.col('v.~label') == f.col('st.c_image_path'))) \
.withColumn("eid", monotonically_increasing_id()) \
.withColumn('~label', lit('similar')) \
.select(f.col('eid').alias('~id'), \
        f.col('vtp.~id').alias('~from'),\
        f.col('v.~id').alias('~to'),\
        f.col('~label'),\
        f.col('st.similarity').alias('similarity:Double')).orderBy(['vtp.~id','similarity:Double'], ascending=[1, 1])

EDGE_DATA_OUTPUT_S3_BUCKET = "s3://sagemaker-us-west-2-803235869972/sagemaker/DEMO-pytorch-siamese-network/gremlin/edges"

edgesDF = edgesDF.repartition(8)
edgesDF.write.csv(EDGE_DATA_OUTPUT_S3_BUCKET, header="true", compression="gzip", mode="overwrite")

job.commit()

/*
 * Copyright 2021 4Paradigm
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com._4paradigm.openmldb.java_sdk_test.executor;

import com._4paradigm.openmldb.test_common.bean.OpenMLDBResult;
import com._4paradigm.openmldb.test_common.util.SDKUtil;
import com._4paradigm.openmldb.sdk.SqlExecutor;
import com._4paradigm.openmldb.test_common.model.SQLCase;
import com._4paradigm.openmldb.test_common.model.SQLCaseType;
import com._4paradigm.openmldb.test_common.util.SQLUtil;
import com._4paradigm.qa.openmldb_deploy.bean.OpenMLDBInfo;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.collections4.CollectionUtils;
import org.apache.commons.lang3.StringUtils;

import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Slf4j
public class StoredProcedureSQLExecutor extends RequestQuerySQLExecutor {

    protected List<String> spNames;

    public StoredProcedureSQLExecutor(SqlExecutor executor, SQLCase fesqlCase, boolean isBatchRequest, boolean isAsyn, SQLCaseType executorType) {
        super(executor, fesqlCase, isBatchRequest, isAsyn, executorType);
        spNames = new ArrayList<>();
    }

    public StoredProcedureSQLExecutor(SQLCase fesqlCase, SqlExecutor executor, Map<String,SqlExecutor> executorMap, Map<String, OpenMLDBInfo> fedbInfoMap, boolean isBatchRequest, boolean isAsyn, SQLCaseType executorType) {
        super(fesqlCase, executor, executorMap, fedbInfoMap, isBatchRequest, isAsyn, executorType);
        spNames = new ArrayList<>();
    }

    @Override
    public OpenMLDBResult execute(String version, SqlExecutor executor) {
        log.info("version:{} execute begin",version);
        OpenMLDBResult fesqlResult = null;
        try {
            if (sqlCase.getInputs().isEmpty() || CollectionUtils.isEmpty(sqlCase.getInputs().get(0).getRows())) {
                throw new IllegalArgumentException("fail to execute in request query sql executor: sql case inputs is empty");
            }
            String sql = sqlCase.getSql();
            log.info("sql: {}", sql);
            if (StringUtils.isEmpty(sql)) {
                throw new IllegalArgumentException("fail to execute in request query sql executor: sql is empty");
            }
            if (sqlCase.getBatch_request() != null) {
                fesqlResult = executeBatch(executor, sql, this.isAsyn);
            } else {
                fesqlResult = executeSingle(executor, sql, this.isAsyn);
            }
            spNames.add(sqlCase.getSpName());
        }catch (Exception e){
            e.printStackTrace();
        }
        log.info("version:{} execute end",version);
        return fesqlResult;
    }

    private OpenMLDBResult executeSingle(SqlExecutor executor, String sql, boolean isAsyn) throws SQLException {
        String spSql = sqlCase.getProcedure(sql);
        log.info("spSql: {}", spSql);
        return SDKUtil.sqlRequestModeWithProcedure(
                executor, dbName, sqlCase.getSpName(), null == sqlCase.getBatch_request(),
                spSql, sqlCase.getInputs().get(0), isAsyn);
    }

    private OpenMLDBResult executeBatch(SqlExecutor executor, String sql, boolean isAsyn) throws SQLException {
        String spName = "sp_" + tableNames.get(0) + "_" + System.currentTimeMillis();
        String spSql = SQLUtil.buildSpSQLWithConstColumns(spName, sql, sqlCase.getBatch_request());
        log.info("spSql: {}", spSql);
        return SDKUtil.selectBatchRequestModeWithSp(
                executor, dbName, spName, spSql, sqlCase.getBatch_request(), isAsyn);
    }


    @Override
    public void tearDown(String version,SqlExecutor executor) {
        log.info("version:{},begin tearDown",version);
        if (CollectionUtils.isEmpty(spNames)) {
            return;
        }
        for (String spName : spNames) {
            String drop = "drop procedure " + spName + ";";
            SDKUtil.ddl(executor, dbName, drop);
        }
        super.tearDown(version,executor);
    }
}

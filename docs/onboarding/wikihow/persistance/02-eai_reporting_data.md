# Persitance

main entry poing for self service test is stored on .env file win machine (personal comment)

### prerequisits

1. contanct help desk for plsql client 
2. get db creds from relevant department 

Example: selfservicetest.hot.net.il -> user : ****  db: d***g

EAI REPORTING DATA

for feature [DD_CR12575](docs/web/feature/DD_CR12575/01-customer-journey) entry point for db documentaion is the eai reporting data table 
seems to work as a log aggreator that unifies request and response status and is the source of procederall truth for the feature (additionaly to Billy system) 


```plsql
# to get main selfservice test activity logs
# TBD better explain purpose of the eai reporting table strictly log aggregator ?
select * from eai_reporting_data order by eai_reporting_data.entry_datetime desc;
```




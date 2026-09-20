import os

path = "c:/Users/anish/Downloads/SIH26168/vizag_nav_app/app/src/main/java/com/vizag/nav/ImuManager.kt"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

bad_string = """    private val accelListener = object : SensorEventListener {
        override fun onSensorChanged(e: SensorEvent) {
            ax = e.values[0]; ay = e.values[1]; az = e.values[2]
            pushSample()
        }
        override fun onAccuracyChanged(s: Sensor?, a: Int) = Unit
    }
        override fun onAccuracyChanged(s: Sensor?, a: Int) = Unit
    }"""
    
good_string = """    private val accelListener = object : SensorEventListener {
        override fun onSensorChanged(e: SensorEvent) {
            ax = e.values[0]; ay = e.values[1]; az = e.values[2]
            pushSample()
        }
        override fun onAccuracyChanged(s: Sensor?, a: Int) = Unit
    }"""

content = content.replace(bad_string, good_string)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

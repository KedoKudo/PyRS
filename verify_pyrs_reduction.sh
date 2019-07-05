#!/bin/sh
python setup.py pyuic
python setup.py build

echo 
MANTIDLOCALPATH=/home/wzz/Mantid_Project/debug/bin/
MANTIDMACPATH=/Users/wzz/MantidBuild/debug/bin/
# MANTIDSNSDEBUGPATH=/SNS/users/wzz/Mantid_Project/builds/debug/bin/
MANTIDPATH=$MANTIDMACPATH:$MANTIDLOCALPATH:$MANTIDSNSDEBUGPATH
PYTHONPATH=$MANTIDPATH:$PYTHONPATH
echo "PYTHON PATH: "
echo $PYTHONPATH
echo


if [ $1 ]; then
    CMD=$1
    CMDS=''
    for file in "$@"
    do
      echo $file
      if [ $file = $1 ] ; 
      then
	  echo "Ignore "
	  echo $file
      else
          CMDS="$CMDS $file"
      fi
    done
else
    CMD=
    echo "Verify PyRS and Mantid Reduction. Options:"
    echo "(1) [compare] geometry (XRay Mock)"
    echo "(2) [compare] 2theta"
    echo "(4) [compare] reduction-all (without masking)"
    echo "(5) [compare] reduction-0   (with ROI on 0 degree)"
    echo "(6) [compare] reduction-10  (with ROI on +10 degree)"
    echo "(7) [compare] reduction-20  (with ROI on +20 degree)"
    echo "(8) [compare] reduction-30  (with ROI on +30 degree)"
    echo "(21) [verify] HBZ geometry: aka HBZ-IDF"
    echo "(111) [study] reduction study"
    echo "(104) reduce-pyrs-all"
    echo "(105) reduce-pyrs-0degree"
    echo "(106) reduce-pyrs-10degree"
    # echo "(5) reduction test on 1024x1024"
    # echo "(8) Peak processing UI test"
    # echo "(9) Prototype: calibraton"
    echo "Options: Test all commands: \"all\""
fi 

echo "User option: $1"

# Ordered by latest test case

if [ "$1" = "21" ] || [ "$1" = "HBZ-IDF" ] ; then
    echo "Comparing and verifying instrument geometry for HBZ (IDF and PyRS configuration)"
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 21
    # PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 22
fi


if [ "$1" = "1" ] || [ "$1" = "geometry" ] ; then
    echo "Comparing instrument geometry"
    # PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 1
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 2
fi

if [ "$1" = "2" ] || [ "$1" = "2theta" ] ; then
    echo "Comparing converted 2theta from geometry"
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 3
    # PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 4
fi


if [ "$1" = "3" ] || [ "$1" = "counts" ] ; then
    echo "With engine changed, no need to compare counts any more"
fi

if [ "$1" = "4" ] || [ "$1" = "reduction-all" ] ; then
    echo "Testing Reduction Without ROI/Mask"
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 5
    # PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 6

fi

if [ "$1" = "5" ] || [ "$1" = "reduction-0" ] ; then
    echo "Testing Reduction with ROI around solid angle 0 degree"
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 7
    # PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 8
fi

if [ "$1" = "6" ] || [ "$1" = "reduction-10" ] ; then
    echo "Testing Reduction with ROI around solid angle +10 degree"
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 9
fi

if [ "$1" = "7" ] || [ "$1" = "reduction-20" ] ; then
    echo "Testing Reduction with ROI around solid angle +20 degree"
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH python ./build/scripts-2.7/compare_reduction_engines_test.py 11
fi


if [ "$1" = "8" ] || [ "$1" = "reduction-30" ] ; then
    echo "Testing Reduction with ROI around solid angle +30 degree"
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH python ./build/scripts-2.7/compare_reduction_engines_test.py 13
fi


if [ "$1" = "111" ] || [ "$1" = "study" ] ; then
    echo "Reducing (histogram) with solid angle 30 mask"
    # PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH python ./build/scripts-2.7/reduction_study.py tests/testdata/LaB6_10kev_35deg-00004_Rotated_TIF.h5 35. tests/testdata/masks/Chi_30.hdf5 pyrs
    # PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH python ./build/scripts-2.7/reduction_study.py tests/testdata/LaB6_10kev_35deg-00004_Rotated_TIF.h5 35. tests/testdata/masks/Chi_Neg30.hdf5 pyrs
    # PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH python ./build/scripts-2.7/reduction_study.py tests/testdata/LaB6_10kev_35deg-00004_Rotated_TIF.h5 35. tests/testdata/masks/Chi_0.hdf5 pyrs
    # PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH python ./build/scripts-2.7/reduction_study.py tests/testdata/LaB6_10kev_35deg-00004_Rotated_TIF.h5 35. tests/testdata/masks/Chi_10.hdf5 pyrs
    # PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH python ./build/scripts-2.7/reduction_study.py tests/testdata/LaB6_10kev_35deg-00004_Rotated_TIF.h5 35. tests/testdata/masks/Chi_20.hdf5 pyrs
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH python ./build/scripts-2.7/reduction_study.py tests/testdata/LaB6_10kev_35deg-00004_Rotated_TIF.h5 35. None pyrs
fi

if [ "$1" = "105" ] || [ "$1" = "reduce-pyrs-0degree" ] ; then
    echo "Testing Reduction with ROI around solid angle +35 degree"
    # PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 11
    # PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 12
    # PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/compare_reduction_engines_test.py 13


    echo "Testing Reduction with ROI around solid angle +35 degree"
    TestArgsMantid=" ./tests/testdata/LaB6_10kev_35deg-00004_Rotated.h5 ./tests/temp/ --viewraw=1  --instrument=tests/testdata/XRay_Definition_2K.xml --2theta=35."
    TestArgsPyRS=" ./tests/testdata/LaB6_10kev_35deg-00004_Rotated.h5 ./tests/temp/ --viewraw=1  --instrument=tests/testdata/XRay_Definition_2K.txt --2theta=35."
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/reduce_HB2B.py $TestArgsPyRS
    TestArgsMantid=" ./tests/testdata/LaB6_10kev_35deg-00004_Rotated.h5 ./tests/temp/ --viewraw=1 --mask=tests/testdata/masks/Chi_0.hdf5 --instrument=tests/testdata/XRay_Definition_2K.xml --2theta=35."
    TestArgsPyRS=" ./tests/testdata/LaB6_10kev_35deg-00004_Rotated.h5 ./tests/temp/ --viewraw=1 --mask=tests/testdata/masks/Chi_0.hdf5 --instrument=tests/testdata/XRay_Definition_2K.txt --2theta=35."
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/reduce_HB2B.py $TestArgsPyRS
fi




if [ "$1" = "99" ] || [ "$1" = "unknown" ] ; then
    TestArgs3=" ./tests/testdata/LaB6_10kev_35deg-00004_Rotated.tif ./tests/temp/ --viewraw=1 --mask=tests/testdata/masks/Chi_0.hdf5 --instrument=tests/testdata/XRay_Definition_2K.xml --2theta=-35."
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/reduce_HB2B.py $TestArgs3
    TestArgs2=" ./tests/testdata/LaB6_10kev_35deg-00004_Rotated.tif ./tests/temp/ --viewraw=1  --instrument=tests/testdata/XRay_Definition_2K.xml --2theta=-35."
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/reduce_HB2B.py $TestArgs2
    TestArgs="--roi=tests/testdata/masks/Chi_0_Mask.xml --output=Chi_0.hdf5 --operation=reverse --2theta=35."
    TestArgs1=" ./tests/testdata/LaB6_10kev_35deg-00004_Rotated.tif ./tests/temp/ --mask=tests/testdata/masks/Chi_0.hdf5 --viewraw=1"

    # Mantid reduction engine
    TestArgs2=" ./tests/testdata/LaB6_10kev_35deg-00004_Rotated.tif ./tests/temp/ --mask=tests/testdata/masks/Chi_0.hdf5 --viewraw=0 --instrument=tests/testdata/XRay_Definition_2K.xml --2theta=-35."
    # TestArgs2=" ./tests/testdata/LaB6_10kev_35deg-00004_Rotated.tif ./tests/temp/ --viewraw=0 --instrument=tests/testdata/XRay_Definition_2K.xml --2theta=-35."
    # PyRS reduction engine
    TestArgs3=" ./tests/testdata/LaB6_10kev_35deg-00004_Rotated.tif ./tests/temp/ --mask=tests/testdata/masks/Chi_30.hdf5 --viewraw=0 --instrument=tests/testdata/xray_data/XRay_Definition_2K.txt --2theta=-35."
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/reduce_HB2B.py $TestArgs2
fi

if [ "$1" = "115" ] || [ "$1" = "reduce1024" ] ; then
    echo "Testing Reduction: 1024 x 1024"
    TestArgs=" ./tests/testdata/LaB6_10kev_35deg-00004_Rotated.bin ./tests/temp/ --mask=tests/testdata/masks/Chi_0.hdf5 --viewraw=0 --instrument=tests/testdata/XRay_Definition_1K.xml --2theta=35."
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH ./build/scripts-2.7/reduce_HB2B.py $TestArgs
fi

if [ "$1" = "9" ] || [ "$1" = "prototype" ] ; then
    echo "Process masks/ROIs"
    PYTHONPATH=build/lib:build/lib.linux-x86_64-2.7:$PYTHONPATH python ./tests/Quick_Calibration_v2.py
fi
